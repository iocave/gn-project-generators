#
# Xcode project model
#

import hashlib
import struct
import collections
import re
import posixpath
from pprint import pprint

# 2.7/3.5 compatibility

try:
    unicode
except NameError:
    unicode = str

try:
    xrange
except NameError:
    xrange = range

#
class PBXObject:    
    
    # hash_parent optionally specifies object that contributes hashable to this PBXObject
    def __init__(self, hash_parent = None):
        self._single_line = False
        self._properties = {}        
        self._hash_parent = hash_parent                
        self._id = None
        self._id_digest = None
        self._hashables = None
    
    def set_property(self, key, value):
        self._properties[key] = value

    def get_property(self, key):
        return self._properties[key]

    def get_name(self):
        return None

    def get_comment(self):
        return self.get_name()
    
    def get_class(self):
        return self.__class__.__name__

    def get_hashables(self):

        if self._hashables is None:
        
            self._hashables = [self.__class__.__name__]

            name = self.get_name()
            if name is not None:
                self._hashables.append(name)

            # Instead of adding all hashables from parent (which can recurse all the way to the top)
            # We use parent Id digest (which is generated from parent hashables and cached)
            # This makes significant performance improvement
            if self._hash_parent is not None:
                self._hashables.append(self._hash_parent.get_id_digest())

            self._hashables.extend(self._additional_hashables())

        return self._hashables
        
    def _additional_hashables(self):
        return []

    # returns complete SHA digest from ID (160bits)
    def get_id_digest(self):

        def compute_id_digest(self):
            sha = hashlib.sha1().copy()
            hashables = self.get_hashables()
            for hashable in hashables:
                data = hashable
                if unicode == str and isinstance(data, unicode):
                    data = data.encode("utf-8")
                sha.update(struct.pack('>i', len(data)))
                sha.update(data)
            return sha.digest()

        if self._id_digest is None:
            self._id_digest = compute_id_digest(self)

        return self._id_digest

    def get_id(self):        

        def compute_id(self):
            digest = self.get_id_digest()
            digest_size = len(digest)

            # Xcode IDs are only 96 bits (24 hex characters), but a SHA-1 digest is
            # is 160 bits.  Instead of throwing out 64 bits of the digest, xor them
            # into the portion that gets used.
            assert digest_size % 4 == 0
            digest_int_count = int(digest_size / 4)
            digest_ints = struct.unpack('>' + 'I' * digest_int_count, digest)
            id_ints = [0, 0, 0]
            for index in xrange(0, digest_int_count):
                id_ints[index % 3] ^= digest_ints[index]
            return '%08X%08X%08X' % tuple(id_ints)
            
        if self._id is None:
            self._id = compute_id(self)

        return self._id
    
    def _should_output_class_name(self):
        return True 

    def write_object(self, indent, file):
        items = collections.OrderedDict()

        if (self._should_output_class_name()):
            items["isa"] = self.__class__.__name__        

        for key, value in sorted(self._properties.items()):
            items[key] = value
        
        PBXObject._write_iterable(items.items(), self._single_line, indent, file)

    @staticmethod 
    def _write_single_property(key, value, single_line, indent, file):
        def write_value(indent, value):
            if isinstance(value, bool):
                if value:
                    file.write("YES")
                else:
                    file.write("NO")  
            elif isinstance(value, int):
                file.write(str(value))
            elif isinstance(value, str):
                file.write(PBXObject._encode_string(value, single_line))
            elif isinstance(value, unicode):
                file.write(PBXObject._encode_string(value, single_line))
            elif isinstance(value, PBXObject):
                value.write_object(indent, file)
            elif isinstance(value, list):
                file.write("(")
                if not single_line:
                    file.write("\n" + "\t" * indent)
                for v in value:
                    if not single_line:
                        file.write("\t")
                    write_value(indent + 1, v)
                    file.write(",")
                    if not single_line:
                        file.write("\n" + "\t" * indent)
                file.write(")")
            else:
                PBXObject._write_iterable(sorted(value.items()), single_line, indent, file)
            
        file.write(key)
        if isinstance(value, PBXObject) and value.get_comment() is not None:
            file.write(" /* ")
            file.write(value.get_comment())
            file.write(" */")
        file.write(" = ")
        write_value(indent + 1, value)
        file.write(";")

    @staticmethod
    def _write_iterable(iterable, single_line, indent, file):

        file.write("{")
        
        first = True
        for key, value in iterable:

            if not first and single_line:
                file.write(" ") # first property does not get separator
            elif not single_line:
                file.write("\n" + "\t" * indent + "\t")

            first = False

            PBXObject._write_single_property(key, value, single_line, indent, file)

        if single_line:
            file.write(" }")
        else:
            file.write("\n" + "\t" * indent + "}")

    # _encode_string - from gyp's xcode_proj.py
    
    _encode_transforms = []
    i = 0
    while i < ord(' '):
        _encode_transforms.append('\\U%04x' % i)
        i = i + 1
    _encode_transforms[7] = '\\a'
    _encode_transforms[8] = '\\b'
    _encode_transforms[9] = '\\t'
    _encode_transforms[10] = '\\n'
    _encode_transforms[11] = '\\v'
    _encode_transforms[12] = '\\f'
    _encode_transforms[13] = '\\n'

    # transforms for single line
    _alternate_encode_transforms = list(_encode_transforms)
    _alternate_encode_transforms[9] = chr(9)
    _alternate_encode_transforms[10] = chr(10)
    _alternate_encode_transforms[11] = chr(11)

    # See XCObject._encode_string.  This pattern is used to determine when a string
    # can be printed unquoted.  Strings that match this pattern may be printed
    # unquoted.  Strings that do not match must be quoted and may be further
    # transformed to be properly encoded.  Note that this expression matches the
    # characters listed with "+", for 1 or more occurrences: if a string is empty,
    # it must not match this pattern, because it needs to be encoded as "".
    _unquoted = re.compile('^[A-Za-z0-9$./_]+$')

    # Strings that match this pattern are quoted regardless of what _unquoted says.
    # Oddly, Xcode will quote any string with a run of three or more underscores.
    _quoted = re.compile('___')

    # This pattern should match any character that needs to be escaped by
    # XCObject._encode_string.  See that function.
    _escaped = re.compile('[\\\\"]|[\x00-\x1f]')

    @staticmethod
    def _encode_string(value, single_line):
        """Encodes a string to be placed in the project file output, mimicking Xcode behavior."""
        
        def encode_transform(match):
            # This function works closely with _EncodeString.  It will only be called
            # by re.sub with match.group(0) containing a character matched by the
            # the _escaped expression.
            char = match.group(0)

            # Backslashes (\) and quotation marks (") are always replaced with a
            # backslash-escaped version of the same.  Everything else gets its
            # replacement from the class' _encode_transforms array.
            if char == '\\':
                return '\\\\'
            if char == '"':
                return '\\"'
            transforms = PBXObject._alternate_encode_transforms if single_line else PBXObject._encode_transforms            
            return transforms[ord(char)]

        # Use quotation marks when any character outside of the range A-Z, a-z, 0-9,
        # $ (dollar sign), . (period), and _ (underscore) is present.  Also use
        # quotation marks to represent empty strings.
        #
        # Escape " (double-quote) and \ (backslash) by preceding them with a
        # backslash.
        #
        # Some characters below the printable ASCII range are encoded specially:
        #     7 ^G BEL is encoded as "\a"
        #     8 ^H BS  is encoded as "\b"
        #    11 ^K VT  is encoded as "\v"
        #    12 ^L NP  is encoded as "\f"
        #   127 ^? DEL is passed through as-is without escaping
        #  - In PBXFileReference and PBXBuildFile objects:
        #     9 ^I HT  is passed through as-is without escaping
        #    10 ^J NL  is passed through as-is without escaping
        #    13 ^M CR  is passed through as-is without escaping
        #  - In other objects:
        #     9 ^I HT  is encoded as "\t"
        #    10 ^J NL  is encoded as "\n"
        #    13 ^M CR  is encoded as "\n" rendering it indistinguishable from
        #              10 ^J NL
        # All other characters within the ASCII control character range (0 through
        # 31 inclusive) are encoded as "\U001f" referring to the Unicode code point
        # in hexadecimal.  For example, character 14 (^N SO) is encoded as "\U000e".
        # Characters above the ASCII range are passed through to the output encoded
        # as UTF-8 without any escaping.  These mappings are contained in the
        # class' _encode_transforms list.

        if PBXObject._unquoted.search(value) and not PBXObject._quoted.search(value):
            return value

        return '"' + PBXObject._escaped.sub(encode_transform, value) + '"'            

class PBXContainer(PBXObject):

    def __init__(self):
        PBXObject.__init__(self)
        self.set_property("archiveVersion", 1)
        self.set_property("classes", { })    
        self.set_property("objectVersion", 46)
        self.set_property("objects", PBXObjects(self))

    def write_object(self, indent, file):
        file.write("// !$*UTF8*$!\n")
        PBXObject.write_object(self, indent, file)
        file.write("\n")

    def get_objects(self):
        return self.get_property("objects")

    def _should_output_class_name(self):
        return False

    def set_root_object(self, root_object):
        self.set_property("rootObject", PBXReference(root_object))

# Represents the Objects section of PBX file - wraps properties
# in /* Begin XXX section */ and /* End XXX section */ comments
class PBXObjects(PBXObject):

    def write_object(self, indent, file):

        file.write("{\n")
        object_by_class = {}

        for key, value in self._properties.items():
            assert(isinstance(value, PBXObject))
            class_name = value.__class__.__name__
            if class_name not in object_by_class:
                object_by_class[class_name] = {}
            object_by_class[class_name][key] = value 

        for class_name, objects in sorted(object_by_class.items()):
            file.write("\n/* Begin " + class_name + " section */\n")

            for key2, value2 in sorted(objects.items()):
                file.write("\t" * (indent + 1))
                PBXObject._write_single_property(key2, value2, False, indent, file)
                file.write("\n")                

            file.write("/* End " + class_name + " section */\n")

        file.write("\t" * indent + "}")

    def _should_output_class_name(self):
        return False

    def add_object(self, o):
        # Assertion here means hash collision
        assert(self._properties.get(o.get_id()) == None)
        self.set_property(o.get_id(), o)
        
class PBXFileReference(PBXObject):
    def __init__(self, parent, file_name, path = None):
        PBXObject.__init__(self, parent)
        self._single_line = True
        if path == None:        
            self.set_property("path", file_name)
        else:
            self.set_property("name", file_name)
            self.set_property("path", path)
            
        self.set_property("sourceTree", "<group>")
        self.ext = posixpath.splitext(file_name)[1]
        if self.ext != "":
            self.ext = self.ext[1:].lower()
        file_type = PBXFileReference.extension_map.get(self.ext, "text")
        if self.ext == "gn" or self.ext == "gni":
            self.set_property("explicitFileType", file_type)
        else:
            self.set_property("lastKnownFileType", file_type)
        
    def get_name(self):
        return self.get_property("path")

    def make_build_product_executable(self):        
        self.set_property("lastKnownFileType", "compiled.mach-o.executable")
        self.set_property("sourceTree", "BUILT_PRODUCTS_DIR")

    def make_build_product_app_bundle(self):
        del self._properties["lastKnownFileType"]
        self.set_property("explicitFileType", "wrapper.application")
        self.set_property("includeInIndex", 0)
        self.set_property("sourceTree", "BUILT_PRODUCTS_DIR")

    extension_map = {
        'a': 'archive.ar',
        'app': 'wrapper.application',
        'bdic': 'file',
        'bundle': 'wrapper.cfbundle',
        'c': 'sourcecode.c.c',
        'cc': 'sourcecode.cpp.cpp',
        'cpp': 'sourcecode.cpp.cpp',
        'css': 'text.css',
        'cxx': 'sourcecode.cpp.cpp',
        'dart': 'sourcecode',
        'dylib': 'compiled.mach-o.dylib',
        'framework': 'wrapper.framework',
        'gyp': 'sourcecode',
        'gypi': 'sourcecode',
        'h': 'sourcecode.c.h',
        'hxx': 'sourcecode.cpp.h',
        'icns': 'image.icns',
        'java': 'sourcecode.java',
        'js': 'sourcecode.javascript',
        'kext': 'wrapper.kext',
        'm': 'sourcecode.c.objc',
        'mm': 'sourcecode.cpp.objcpp',
        'nib': 'wrapper.nib',
        'o': 'compiled.mach-o.objfile',
        'pdf': 'image.pdf',
        'pl': 'text.script.perl',
        'plist': 'text.plist.xml',
        'pm': 'text.script.perl',
        'png': 'image.png',
        'py': 'text.script.python',
        'r': 'sourcecode.rez',
        'rez': 'sourcecode.rez',
        's': 'sourcecode.asm',
        'storyboard': 'file.storyboard',
        'strings': 'text.plist.strings',
        'swift': 'sourcecode.swift',
        'ttf': 'file',
        'xcassets': 'folder.assetcatalog',
        'xcconfig': 'text.xcconfig',
        'xcdatamodel': 'wrapper.xcdatamodel',
        'xcdatamodeld': 'wrapper.xcdatamodeld',
        'xib': 'file.xib',
        'y': 'sourcecode.yacc',
        'gn': 'text.script.perl', # should work well enough
        'gni': 'text.script.perl',
    }

class PBXFrameworkBuildPhase(PBXObject):
    def __init__(self, parent):
        PBXObject.__init__(self, parent)                        

    def get_name(self):
        return "Frameworks"

class PBXSourcesBuildPhase(PBXObject):
    def __init__(self, parent):
        PBXObject.__init__(self, parent)
        self.set_property("buildActionMask", 2147483647)
        self.set_property("runOnlyForDeploymentPostprocessing", 0)
        self.set_property("files", [])

    def get_name(self):
        return "Sources"

    def add_file(self, build_file):
        self.get_property("files").append(PBXReference(build_file))

class PBXBuildFile(PBXObject):
    def __init__(self, parent, file_ref, build_phase):
        PBXObject.__init__(self, parent)
        self._single_line = True
        self._file_ref = file_ref
        self._build_phase = build_phase
        self.set_property("fileRef", PBXReference(file_ref))

    def get_comment(self):
        return self._file_ref.get_name() + " in " + self._build_phase.get_name()

    def name(self):
        return self._file_ref.get_name() 

    def _additional_hashables(self):
        l = []        
        l.extend(self._file_ref.get_hashables())
        l.extend(self._build_phase.get_hashables())
        return l

class PBXProject(PBXObject):
    def __init__(self, parent, name):
        PBXObject.__init__(self, parent)
        self.name = name

        self.set_property("attributes", {
            "BuildIndependentTargetsInParallel" : True,
            "LastUpgradeCheck" : "0800"
        })
        self.set_property("compatibilityVersion", "Xcode 3.2")
        self.set_property("developmentRegion", "English")
        self.set_property("hasScannedForEncodings", 1)
        self.set_property("knownRegions", ["en"])
        self.set_property("projectDirPath", "")
        self.set_property("projectRoot", "")
        self.set_property("targets", [])

    def get_name(self):
        return self.name

    def get_comment(self):   
        return "Project object"

    def add_target(self, target):
        self.get_property("targets").append(PBXReference(target))

    def set_build_configuration_list(self, bcl):
        self.set_property("buildConfigurationList", PBXReference(bcl))

    def set_main_group(self, group):
        self.set_property("mainGroup", PBXReference(group))
        self.set_property("productRefGroup", PBXReference(group))

    def write_object(self, indent, file):
        targets = self.get_property("targets")
        targets.sort(key = lambda t : t.referenced_object.get_name())
        PBXObject.write_object(self, indent, file)

class XCBuildConfiguration(PBXObject):
    def __init__(self, parent, name):
        PBXObject.__init__(self, parent)
        self.set_property("name", name)
        self.set_property("buildSettings", {})
        
    def get_name(self):
        return self.get_property("name")

    def build_settings(self):
        return self.get_property("buildSettings")

class XCConfigurationList(PBXObject):
    def __init__(self, parent, target):
        PBXObject.__init__(self, parent)
        self.target = target
        self.set_property("buildConfigurations", [])

    def add_build_configuration(self, configuration):
        self.get_property("buildConfigurations").append(PBXReference(configuration))

    def get_name(self):        
        return "Build configuration list for " + self.target.__class__.__name__ + " \"" + self.target.get_name() + "\""

class PBXGroup(PBXObject):
    def __init__(self, parent, name = None, path = None):
        PBXObject.__init__(self, parent)        

        if path is None:
            path = name

        self.name = name
        self.path = path

        if self.path is not None:
            self.set_property("path", self.path)
        
        if self.name is not None and self.name != self.path:
            self.set_property("name", self.name)

        self.set_property("sourceTree", "<group>")
        self.set_property("children", [])

        self._child_map = {}
        
    def add_child(self, group):
        self.get_property("children").append(PBXReference(group))
        self._child_map[group.get_name()] = group

    def get_child(self, name):
        return self._child_map.get(name, None)        

    def get_name(self):
        return self.name

    def _additional_hashables(self):
        l = []
        if self.path is not None:
            l.extend([self.path])
        return l

    def write_object(self, indent, file):
   
        # python 2.7 does not have casefold, we'll use lower() instead
        cf = lambda x : x.casefold()
        try:
            "".casefold()
        except AttributeError:
            cf = lambda x : x.lower()

        def sort_key(x):
            ref = x.referenced_object
            prefix = "1" if isinstance(ref, PBXGroup) else "2"
            return prefix + cf(ref.get_name())

        children = self.get_property("children")        
        children.sort(key=sort_key)
        PBXObject.write_object(self, indent, file)

class PBXNativeTarget(PBXObject):
    def __init__(self, parent, name, product_name, product_type):
        PBXObject.__init__(self, parent)
        self.set_property("name", name)
        self.set_property("productName", product_name)
        self.set_property("buildPhases", [])
        self.set_property("buildRules", [])        
        self.set_property("productType", product_type)

    def get_name(self):
        return self.get_property("name")

    def add_build_phase(self, build_phase):
        self.get_property("buildPhases").append(PBXReference(build_phase))

    def set_build_configuration_list(self, bcl):
        self.set_property("buildConfigurationList", PBXReference(bcl))

class PBXLegacyTarget(PBXObject):
    def __init__(self, parent, name, buildToolPath, buildArgumentsString, buildWorkingDir):

        PBXObject.__init__(self, parent)
        self.set_property("name", name)
        self.set_property("buildToolPath", buildToolPath)        
        self.set_property("buildArgumentsString", buildArgumentsString)
        self.set_property("buildWorkingDirectory", buildWorkingDir)
        self.set_property("buildPhases", [])
        self.set_property("dependencies", [])
        self.set_property("passBuildSettingsInEnvironment", 1)
        self.set_property("productName", name)

    def get_name(self):
        return self.get_property("name")

    def set_build_configuration_list(self, bcl):
        self.set_property("buildConfigurationList", PBXReference(bcl))

    def set_product_reference(self, ref):
        self.set_property("productReference", PBXReference(ref))

# Intermediate object that renders reference (just ID + comment) to another PBXObject
class PBXReference(PBXObject):
    def __init__(self, referenced_object):
        PBXObject.__init__(self, None)
        self.referenced_object = referenced_object
    
    def write_object(self, indent, file):
        file.write(self.referenced_object.get_id())
        comment = self.referenced_object.get_comment()
        if comment is not None:
            file.write(" /* ")
            file.write(comment)
            file.write(" */")
