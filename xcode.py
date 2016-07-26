#!/usr/bin/env python

#
# XCode project generator
#

import json
import os
import sys

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

from pprint import pprint

from impl.pbx import *
from impl.common import *

class ProjectGenerator:

    def __init__(self, project_definition, project_name):
        
        self.project_definition = project_definition

        self.container = PBXContainer()

        # every build object must be added to self.objects
        self.objects = self.container.get_objects()
        
        self.project = PBXProject(self.objects, project_name)

        self.objects.add_object(self.project)

        self.project_bcl = XCConfigurationList(self.objects, self.project)
        self.objects.add_object(self.project_bcl)

        self.project_bc = XCBuildConfiguration(self.project_bcl, "Default")

        self.objects.add_object(self.project_bc)
        self.project_bcl.add_build_configuration(self.project_bc)
    
        self.project_bcl.set_property("defaultConfigurationIsVisible", 1)
        self.project_bcl.set_property("defaultConfigurationName", self.project_bc.get_name())
        
        self.project.set_build_configuration_list(self.project_bcl)        
                
        self.main_group = PBXGroup(self.objects)
        self.objects.add_object(self.main_group)
            
        self.project.set_main_group(self.main_group)

        self.container.set_root_object(self.project) 

    def get_project_name(self):
        return self.project.get_name()

    def group_for_path(self, path):

        # For root items and items in output folder (args.gn) use main group
        if (path == "//" or
            (path + "/") == self.project_definition.build_dir):
            return self.main_group

        assert path.startswith("//")
        path = path[2:]
        
        segments = path.split("/")                

        current_parent = self.main_group
        for segment in segments:
            group = current_parent.get_child(segment)
            if group is None:
                path = None

                # We override path for root groups
                if current_parent == self.main_group:
                    root = self.project_definition.get_relative_path("//")
                    path = root + "/" + segment

                group = PBXGroup(current_parent, segment, path)
                current_parent.add_child(group)
                self.objects.add_object(group)
            current_parent = group

        return current_parent
        
    def _extract_dialect(self, current_value, flags, is_cc):
        if current_value is None:            
            for flag in flags:
                if (flag.startswith("-std=")):
                    current_value = flag[5:]
                    break

        # we're looking for c++ dialect, it must have + in name
        if current_value is not None and is_cc and current_value.find("+") == -1:
            current_value = None
        
        # we're looking for c dialect, it must not have + in name
        if current_value is not None and not is_cc and current_value.find("+") != -1:
            current_value = None

        return current_value
    
    #
    # Indexing targets
    #

    def _generate_indexing_target(self, project_target, compilable_references):
        name = project_target.name        
        name = name[2:]
        product_name = name.replace("/", "_")
        product_name = name.replace(":", "_")

        # create native target for static library and add it to project
        native_target = PBXNativeTarget(self.objects, name, product_name, "com.apple.product-type.library.static")
        self.objects.add_object(native_target)
        self.project.add_target(native_target)
                 
        # create source build phase and add it to target
        sources_bf = PBXSourcesBuildPhase(native_target)
        self.objects.add_object(sources_bf)
        native_target.add_build_phase(sources_bf)
        
        # add build files to source build phase
        for reference in compilable_references:
            build_file = PBXBuildFile(sources_bf, reference, sources_bf)
            sources_bf.add_file(build_file)
            self.objects.add_object(build_file)

        # add build configuration list to target
        target_bcl = XCConfigurationList(native_target, native_target)        
        self.objects.add_object(target_bcl)
        native_target.set_build_configuration_list(target_bcl)
        
        # add build configuration to build configuration list
        target_bc = XCBuildConfiguration(target_bcl, "Default")
        self.objects.add_object(target_bc)
        target_bcl.add_build_configuration(target_bc)

        target_bcl.set_property("defaultConfigurationIsVisible", 0)
        target_bcl.set_property("defaultConfigurationName", target_bc.get_name())

        header_search_paths = []
        for path in project_target.include_dirs:
            header_search_paths.append(self.project_definition.get_relative_path(path))

        target_bc.build_settings().update({
            "HEADER_SEARCH_PATHS" : header_search_paths,
            "GCC_PREPROCESSOR_DEFINITIONS" : project_target.defines,
            "PRODUCT_NAME" : product_name,
            "COMBINE_HIDPI_IMAGES" : "YES"
        })

        # try to extract dialect
        dialect_c = self._extract_dialect(None, project_target.cflags_c, False)
        dialect_c = self._extract_dialect(dialect_c, project_target.cflags_objc, False)
        dialect_c = self._extract_dialect(dialect_c, project_target.cflags, False)        
        dialect_cc = self._extract_dialect(None, project_target.cflags_cc, True)
        dialect_cc = self._extract_dialect(dialect_cc, project_target.cflags_objcc, True)
        dialect_cc = self._extract_dialect(dialect_cc, project_target.cflags, True)

        if dialect_c is not None:
            target_bc.build_settings().update({"GCC_C_LANGUAGE_STANDARD" : dialect_c })
        if dialect_cc is not None:
            target_bc.build_settings().update({"CLANG_CXX_LANGUAGE_STANDARD" : dialect_cc })

        precompiled_header = project_target.get_precompiled_header()
        if precompiled_header is not None:
            target_bc.build_settings().update({
                "GCC_PREFIX_HEADER" : project_target.project.get_relative_path(precompiled_header),
                "GCC_PRECOMPILE_PREFIX_HEADER" : "YES",                
                "GCC_INCREASE_PRECOMPILED_HEADER_SHARING" : "YES", # Allow sharing headers between targets
                "PRECOMPS_INCLUDE_HEADERS_FROM_BUILT_PRODUCTS_DIR" : "NO"
            })

    def generate_targets_for_indexing(self):

        # global settings for indexing
        self.project_bc.build_settings().update({
            "USE_HEADERMAP" : "NO"
        })

        done_sources = set()

        for target_name, target in self.project_definition.targets.items():
        
            # only deal with buildable targets
            if (target.type != TargetType.executable and
                target.type != TargetType.static_library and
                target.type != TargetType.shared_library and
                target.type != TargetType.loadable_module and
                target.type != TargetType.source_set and
                target.type != TargetType.build_dir): 
                continue

            # ignore non default targets
            if target.toolchain != self.project_definition.default_toolchain:
                continue

            compilable_references = []

            sources = list(target.sources)
            if target.get_precompiled_header():                
                sources.append(target.get_precompiled_header())                

            for source in sources:

                # only deal with single source once, even if it is in multiple targets;
                # we don't really care, it only needs to be indexed once
                if source in done_sources:
                    continue
                done_sources.add(source)

                folder_path, file_name = posixpath.split(source)
                group = self.group_for_path(folder_path)
                
                # add file reference for the source if not there yet
                file = group.get_child(file_name)
                if file is None:

                    path = None

                    if group == self.main_group:
                        root = self.project_definition.get_relative_path("//")                        
                        path = root + "/" + source[2:]                        

                    file = PBXFileReference(group, file_name, path)
                    group.add_child(file)
                    self.objects.add_object(file)

                    ext = file.ext                    
                    if ext in set(['c', 'cc', 'cxx', 'cpp', 'm', 'mm']):
                        compilable_references.append(file)

            # we have some compilable sources, create xcode target to index it
            if len(compilable_references) != 0:
                self._generate_indexing_target(target, compilable_references)

    #
    # Product targets
    #

    def _generate_product_target(self, target_name, output_name, output_dir, is_bundle):
            
        # Use output name as target name because it is shorter, as long as there isn't 
        # target with such name already
        xcode_target_name = output_name
        if xcode_target_name in self._target_names:
            xcode_target_name = target_name[2:] # remove //
        self._target_names.add(xcode_target_name)

        legacy_target = PBXLegacyTarget(self.objects, xcode_target_name, 
                                        "/usr/bin/python", 
                                        "invoke_ninja.py " + target_name + " $(ACTION)",
                                         "$(PROJECT_DIR)")
        self.objects.add_object(legacy_target)
        self.project.add_target(legacy_target)

        # add build configuration list to target
        target_bcl = XCConfigurationList(legacy_target, legacy_target)        
        self.objects.add_object(target_bcl)
        legacy_target.set_build_configuration_list(target_bcl)
        
        # add build configuration to build configuration list
        target_bc = XCBuildConfiguration(target_bcl, "Default")
        self.objects.add_object(target_bc)
        target_bcl.add_build_configuration(target_bc)

        target_bcl.set_property("defaultConfigurationIsVisible", 0)
        target_bcl.set_property("defaultConfigurationName", target_bc.get_name())

        relative_output_dir = self.project_definition.get_relative_path(output_dir)
        if relative_output_dir == "" or relative_output_dir == ".":
            build_dir = "$(PROJECT_DIR)"
        else:
            build_dir = "$(PROJECT_DIR)/" + relative_output_dir
        
        target_bc.build_settings().update({
            "CONFIGURATION_BUILD_DIR" : build_dir,
            "PRODUCT_NAME" : output_name
        })

        file_ref = PBXFileReference(legacy_target, output_name)
        if is_bundle:    
            file_ref.make_build_product_app_bundle()
        else:
            file_ref.make_build_product_executable()

        self.objects.add_object(file_ref)
        self.main_group.add_child(file_ref)

        legacy_target.set_product_reference(file_ref)

    # returns True if target is direct dependency of bundle_data target; we use this to remove
    # executable targets that will be part of bundle
    def _target_is_dependency_of_bundle_data(self, target_name):
        for n, target in self.project_definition.targets.items():
            if (target.type == TargetType.bundle_data and
                target_name in target.deps):
                return True
        return False

    def generate_targets_for_products(self):

        self._target_names = set()

        for target_name, target in self.project_definition.targets.items():

            if target.toolchain != self.project_definition.default_toolchain:
                continue

            if (target.type == TargetType.executable and 
                not self._target_is_dependency_of_bundle_data(target_name)):
                                
                output_name = target.get_output_name()
                output_dir = target.get_output_dir()

                self._generate_product_target(target_name, output_name, output_dir, False)
            
            elif target.type == TargetType.create_bundle:

                if (target.bundle_data.get("product_type", "") == "com.apple.product-type.application"):
                    app_dir, app_name = posixpath.split(target.bundle_data["root_dir_output"])

                    self._generate_product_target(target_name, app_name, app_dir, True)    

    def write_build_script(self):

        path = posixpath.join(get_script_dir(), "../tools/invoke_ninja.py")
        with open(path) as f:
            content = f.read()
            
            script_file = self.project_definition.get_absolute_build_path() + "invoke_ninja.py"
            overwrite_file_if_different(script_file, content)

    #
    #
    #

    def write(self):
        
        output = StringIO()
        self.container.write_object(0, output)
        new_content = output.getvalue()
        
        project_folder = self.project_definition.get_absolute_build_path() + self.project.get_name() + ".xcodeproj"
        if not os.path.exists(project_folder):
            os.makedirs(project_folder)
    
        project_file = project_folder + "/project.pbxproj"
        if not overwrite_file_if_different(project_file, new_content):
            print("No changes detected - will not overwrite project file for " + self.project.get_name())
        
        output.close()

#
#
#

class WorkspaceGenerator:

    def __init__(self, project_definition, workspace_name, project_generators):
        self.workspace_name = workspace_name
        self.project_definition = project_definition
        self.project_generators = project_generators        

    def write(self):

        output = StringIO()
        output.write("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
        output.write("<Workspace version = \"1.0\">\n")
        for gen in self.project_generators:
            output.write("  <FileRef location = \"group:" + gen.get_project_name() + ".xcodeproj\"></FileRef>\n")
        output.write("</Workspace>\n")

        new_content = output.getvalue()

        workspace_folder = self.project_definition.get_absolute_build_path() + self.workspace_name + ".xcworkspace"
        if not os.path.exists(workspace_folder):
            os.makedirs(workspace_folder)
    
        project_file = workspace_folder + "/contents.xcworkspacedata"
        if not overwrite_file_if_different(project_file, new_content):
            print("No changes detected - will not overwrite workspace file")
        
        output.close()        
        
def run():

    if len(sys.argv) != 2 and len(sys.argv) != 3:
        print("Usage: " + sys.argv[0] + " <path-to-json-file> [workspace-name]")
        exit(1)
    
    path_to_file = sys.argv[1]
    workspace_name = "Workspace" 
    if len(sys.argv) == 3:
        workspace_name = sys.argv[2]
    
    with open(path_to_file, "r") as json_file:
        v = json_file.read()
        json_file.close()
        js = json.loads(v)
        
        project = Project(js)
            
        gen_sources = ProjectGenerator(project, "Sources")
        gen_sources.generate_targets_for_indexing()            
        gen_sources.write()

        gen_products = ProjectGenerator(project, "Products")
        gen_products.generate_targets_for_products()        
        gen_products.write()
        gen_products.write_build_script()

        # Put products first so that when xcode autogenerates schemes product schemes 
        # (which are actually relevant) are placed first
        gen_workspace = WorkspaceGenerator(project, workspace_name, [gen_products, gen_sources])
        gen_workspace.write()

run()
#import cProfile
#cProfile.run("run()")