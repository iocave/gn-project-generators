#
# Generic Target and Project representation
#

try:
    from enum import Enum
except ImportError:
    from enum34 import Enum

try:
    unicode
except NameError:
    unicode = str

import posixpath
import os

class TargetType(Enum):
    unknown = 0
    group = 1
    executable = 2
    loadable_module = 3
    shared_library = 4
    static_library = 5
    source_set = 6
    copy = 7
    action = 8
    action_foreach = 9
    bundle_data = 10
    create_bundle = 11
    build_dir = -1 # special target containing files from build directory

class Target:
    def __init__(self, name, json_data, project):

        self.project = project

        self.sources = json_data.get("sources", [])
        self.inputs = json_data.get("inputs", [])
        self.arflags = json_data.get("arflags", [])
        self.asmflags = json_data.get("amflags", [])
        self.cflags = json_data.get("cflags", [])
        self.cflags_c = json_data.get("cflags_c", [])
        self.cflags_cc = json_data.get("cflags_cc", [])
        self.cflags_objc = json_data.get("cflags_objc", [])
        self.cflags_objcc = json_data.get("cflags_objcc", [])
        self.defines = json_data.get("defines", [])
        self.include_dirs = json_data.get("include_dirs", [])
        self.ldflags = json_data.get("ldflags", [])
        self.lib_dirs = json_data.get("lib_dirs", [])
        self.libs = json_data.get("libs", [])
        self.deps = json_data.get("deps", [])
        self.precompiled_header = json_data.get("precompiled_header", None)
        self.precompiled_source = json_data.get("precompiled_source", None)
        self.outputs = json_data.get("outputs", [])
        self.output_dir = json_data.get("output_dir", None)
        self.output_name = json_data.get("output_name", None)
        self.output_extension = json_data.get("output_extension", None)
        self.bundle_data = json_data.get("bundle_data", None)
        self.type = TargetType[json_data["type"].lower()]
        self.toolchain = json_data["toolchain"]
        self.source_outputs = json_data.get("source_outputs", {})
        self.name = name
        self._source_dir = None
        self._base_name = None
        self._obj_dir = None

    def get_output_name(self):

        base_name = self.output_name
        if base_name is None: # extract name from target
            base_name = self.get_base_name()

        if self.output_extension is not None:
            base_name = os.path.splitext(base_name)[0]
            if self.output_extension != "":
                base_name += "." + self.output_extension

        return base_name

    def get_base_name(self):
        if self._base_name is None:
            base_name = posixpath.basename(self.name)
            sep = base_name.rfind(":")
            if sep != -1:
                base_name = base_name[sep+1:]
            self._base_name = base_name
        return self._base_name

    def get_source_dir(self):
        if self._source_dir is None:
            index = self.name.rindex(":")
            name = self.name[:index]
            if not name.endswith("/"):
                name += "/"
            self._source_dir = name
        return self._source_dir

    def get_obj_dir(self):
        if self._obj_dir is None:
            source = self.get_source_dir()
            source = source[2:]
            self._obj_dir = self.project.build_dir + "obj" + "/" + source
        return self._obj_dir

    def get_output_dir(self):
        res = self.output_dir
        if res is None:
            res = self.project.build_dir

        return res

class Project:
    def __init__(self, json_data):
        build_settings = json_data["build_settings"]
        self.root_path = build_settings["root_path"]
        self.build_dir = build_settings["build_dir"]
        self.default_toolchain = build_settings["default_toolchain"]

        self.targets = {}
        for key, value in json_data["targets"].items():
            self.targets[key] = Target(key, value, self)

        # Build files are a bit special; we load all build files that gn know about
        # Build files belonging to target folders will be added to respective target sources
        # For build files in //build/ folder we load all surrounding files, as the .gn and .gni
        # files may include scripts and resources gn does not known about
        self.build_files = []
        with open(self.get_absolute_build_path() + "build.ninja.d", "r") as f:
            l = f.readline()
            args = l.split(" ")
            root_path = self.root_path
            if not root_path.endswith("/"):
                root_path += "/"

            known_build_files = set(args)
            processed_dirs = set()

            for arg in args:
                if arg.startswith(self.root_path):
                    short_name = "//" + arg[len(root_path):]
                    self.build_files.append(short_name)
                    dir = posixpath.dirname(arg)
                    if short_name.startswith("//build/") and not dir in processed_dirs:
                        processed_dirs.add(dir)

                        for file in os.listdir(dir):
                            ext = posixpath.splitext(file)[1]
                            if ext == ".pyc":
                                continue
                            path = dir + "/" + file
                            if not path in known_build_files and os.path.isfile(path):
                                short_name = "//" + path[len(root_path):]
                                self.build_files.append(short_name)
                                known_build_files.add(path)

        # Go through targets and add build files belonging to those
        for target_name, target in self.targets.items():
            source_dir = target.get_source_dir()
            for file in self.build_files:
                path = posixpath.dirname(file) + "/"
                if source_dir == path:
                    target.sources.append(file)

        # create build target
        build_target = Target("//build:build", {"type" : "build_dir", "toolchain" : self.default_toolchain}, self)
        for build_file in self.build_files:
            if (build_file.startswith(build_target.get_source_dir()) or
                posixpath.dirname(build_file) == "//" or # Also add root files to build dir
                build_file == self.build_dir + "args.gn"):
                build_target.sources.append(build_file)
        self.targets[build_target.name] = build_target

        #print(build_target.sources)

    # Converts project path relative to build folder

    def get_relative_path(self, path):
        if path.startswith("//"): # project relative
            return posixpath.relpath(self.get_absolute_path(path),
                                     self.get_absolute_build_path())
        else:
            return path # absolute, just return the path

    def get_absolute_build_path(self):
        return self.root_path + "/" + self.build_dir[2:]

    def get_absolute_path(self, path):
        if path.startswith("//"): # project relative
            return self.root_path + "/" + path[2:]
        else:
            return path # absolute

def overwrite_file_if_different(path, new_content):
    overwrite = True

    if (os.path.exists(path)):
        with open(path) as existing_file:
            exiting_content = existing_file.read()
            if exiting_content == new_content:
                overwrite = False
            existing_file.close()

    if overwrite:
        f = open(path, "w")
        f.write(new_content)
        f.close()
        return True
    else:
        return False
