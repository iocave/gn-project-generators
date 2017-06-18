import io
import uuid
from .common import *
from . import easy_xml

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

class ProjectGenerator:

    def __init__(self, project_definition, solution_name, tools_version, platform_toolset, target_platform_version=None):
        self.project_definition = project_definition
        self.solution_name = solution_name
        self.tool_version = tools_version
        self.platform_toolset = platform_toolset
        self.configuration_name = None
        self.target_platform_version = target_platform_version

        path_to_lock = posixpath.normpath(posixpath.join(get_script_dir(), "../tools/directory_lock.exe"))

        if path_to_lock.startswith(self.project_definition.root_path.lower()):
            # directory-lock is within project, use relative path
            path_to_lock = posixpath.relpath(path_to_lock, self.project_definition.get_absolute_build_path().lower())

        # Relative paths need to be in windows format, otherwise .. prefix won't be handled correctly
        self.directory_lock_path = path_to_lock.replace("/", "\\")

    def generate(self):

        targets = []

        for name, target in self.project_definition.targets.items():

            if target.toolchain != self.project_definition.default_toolchain: # ignore non default targets
                continue

            if (target.type == TargetType.executable or
                target.type == TargetType.shared_library or
                target.type == TargetType.static_library or
                target.type == TargetType.loadable_module or
                target.type == TargetType.source_set or
                target.type == TargetType.build_dir):
                self._write_project(target)
                targets.append(target)

        self._write_solution(targets)
        return len(targets)

    def _configuration_type_for_target(self, target):
        if target.type == TargetType.executable:
            return "Application"
        elif target.type == TargetType.shared_library or target.type == TargetType.loadable_module:
            return "DynamicLibrary"
        elif target.type == TargetType.static_library or target.type == TargetType.source_set:
            return "StaticLibrary"
        return "Application" # default for unknown or build targets

    def _target_relative_path(self, target, path):
        return posixpath.relpath(self.project_definition.get_absolute_path(path),
                                 self.project_definition.get_absolute_path(target.get_obj_dir()))

    def _project_file_path(self, target):
        return target.get_obj_dir() + target.get_base_name() + ".vcxproj"

    def _project_uuid(self, target):
        path = str(self._project_file_path(target))
        id = uuid.uuid5(uuid.UUID('7a64fe6e-cba3-5019-90fa-640c295a343e'), path)
        return id

    def _get_platform(self):
        return "x64" if self.project_definition.default_toolchain.endswith(":x64") else "Win32"

    def _write_project(self, target):
        if self.configuration_name == None:
            debug = "_DEBUG" in target.defines or "DEBUG" in target.defines
            self.configuration_name = "Debug" if debug else "Release"

        pr = ["Project", {"DefaultTargets": "Build",
                          "ToolsVersion": self.tool_version,
                          "xmlns": "http://schemas.microsoft.com/developer/msbuild/2003"}]

        platform = self._get_platform()

        configurations = ["ItemGroup", {"Label": "ProjectConfigurations"},
                            ["ProjectConfiguration", { "Include":self.configuration_name+"|" + platform},
                            ["Configuration", self.configuration_name],
                            ["Platform", platform]]]
        pr.append(configurations)

        project_uuid = self._project_uuid(target)

        globals = ["PropertyGroup", {"Label": "Globals"},
                    ["ProjectGuid", "{" + str(project_uuid) + "}"],
                    ["Keyword", "Win32Proj"],
                    ["RootNamespace", target.get_base_name()]]

        if self.target_platform_version:
            globals.append(["WindowsTargetPlatformVersion", self.target_platform_version])

        pr.append(globals)

        pr.append(["Import", {"Project": "$(VCTargetsPath)\\Microsoft.Cpp.Default.props"}])

        configuration = ["PropertyGroup", {"Label": "Configuration"},
                    ["CharacterSet", "Unicode"],
                    ["ConfigurationType", self._configuration_type_for_target(target)],
                    ["PlatformToolset", self.platform_toolset]]
        pr.append(configuration)

        pr.append(["Import", {"Project": "$(VCTargetsPath)\\Microsoft.Cpp.props"}])

        other_props = ["PropertyGroup",
                        ["OutDir", self._target_relative_path(target, self.project_definition.build_dir) +"/"]]
        pr.append(other_props)

        additional_options = []
        for flag in target.cflags:
            if flag.startswith("/FI"):
                additional_options.append(flag)

        include_dirs = []
        for dir in target.include_dirs:
            include_dirs.append(self._target_relative_path(target, dir))
        include_dirs.append("%(AdditionalIncludeDirectories)")
        defines = target.defines + ["%(PreprocessorDefinitions)"]

        compile_options = ["ClCompile",
                                ["AdditionalIncludeDirectories", ";".join(include_dirs)],
                                ["PreprocessorDefinitions", ";".join(defines)]]

        if len(additional_options) > 0:
            compile_options.append(["AdditionalOptions", " ".join(additional_options)])

        pr.append(["ItemDefinitionGroup", compile_options])

        build_group = ["ItemGroup"]

        sources = list(target.sources)

        if target.get_precompiled_header():
            sources.append(target.get_precompiled_header())

        filter_group_files = ["ItemGroup"]
        filter_group_filters = ["ItemGroup"]
        existing_filters = set()
        target_source_dir = target.get_source_dir()

        for source in sources:
            name, ext = posixpath.splitext(source)
            path = self._target_relative_path(target, source)
            filter_entry = None
            if ext in set(['.c', '.cc', '.cxx', '.cpp']):

                compile = ["ClCompile", {"Include": path}]
                filter_entry = list(compile)

                if source != target.precompiled_source:
                    output = target.source_outputs.get(source, "None")
                    if output is not None and len(output) >= 1:
                        compile.append(["OutputFile", output[0]])

                if target.precompiled_header is not None:

                    # This makes assumption about what the precompiled header name looks like, but there's currently
                    # no way to get it from gn so hopefully it won't change in FutureWarning
                    suffix = "c" if ext == ".c" else "cc"
                    precompiled_path = target.get_obj_dir() + target.get_base_name() + "_" + suffix + ".pch"

                    if source == target.precompiled_source:
                        compile.append(["PrecompiledHeader", "Create"])
                    else:
                        compile.append(["PrecompiledHeader", "Use"])

                    compile.append(["PrecompiledHeaderFile", target.precompiled_header])

                    path = self._target_relative_path(target, precompiled_path)
                    compile.append(["PrecompiledHeaderOutputFile", path])

                build_group.append(compile)

            elif ext in set([".h", ".hh", ".hpp"]):
                include = ["ClInclude", {"Include":path}]
                build_group.append(include)
                filter_entry = list(include)

            else:
                none = ["None", {"Include":path}]
                build_group.append(none)
                filter_entry = list(none)

            if filter_entry is not None:
                dir = posixpath.relpath(posixpath.dirname(source), target_source_dir)

                if dir == ".":
                    dir = ""

                appended = False

                while len(dir) > 0:
                    win_dir = dir.replace("/", "\\")
                    if not win_dir in existing_filters:
                        existing_filters.add(win_dir)
                        id = uuid.uuid5(project_uuid, str(win_dir))
                        filter_group_filters.append(["Filter", {"Include":win_dir},
                                                        ["UniqueIdentifier", "{" + str(id) + "}"]])

                    # only filter once, do not append parent folders
                    if not appended:
                        filter_entry.append(["Filter", win_dir])
                        appended = True

                    # filters need to be created for parent folders as well if missing
                    len_before = len(dir)
                    dir = posixpath.normpath(posixpath.join(dir, ".."))

                    # if len after appending .. is greater than before we're going too far (i.e. ../../)
                    if dir == "." or len(dir) > len_before:
                        dir = ""

                filter_group_files.append(filter_entry)

        # For executable targets, try to determine dependency prefix which we can use as base
        # for %path%; It would be much better if this could be passed from GN, but there's currently no
        # mechanism that would allow arbitrary arguments for generators

        extra_path = None

        if target.type == TargetType.executable:
            for lib_dir in target.lib_dirs:
                if lib_dir.find("Program Files") == -1:
                    include = posixpath.normpath(posixpath.join(lib_dir, "../include"))
                    if include in target.include_dirs or (include + "/") in target.include_dirs:
                        bin = posixpath.normpath(posixpath.join(lib_dir, "../bin"))
                        if os.path.isdir(bin):
                            extra_path = bin
                            break

        if extra_path:
            pr.append(["PropertyGroup",
                ["LocalDebuggerEnvironment", "path=%path%;" + extra_path],
                ["DebuggerFlavor", "WindowsLocalDebugger"]])

        pr.append(build_group)

        pr.append(["Import", {"Project": "$(VCTargetsPath)\\Microsoft.Cpp.targets"}])
        pr.append(["ImportGroup", {"Label": "ExtensionTargets"}])

        # Only add custom build rules for regular targets, ignore build target
        # which is not something that ninja knows about
        if target.type != TargetType.build_dir:

            build_target_name = target.name[2:]
            build_target = ["Target", {"Name": "Build"},
                            ["Exec", {"Command": self.directory_lock_path + " . ninja.exe " +  build_target_name,
                            "WorkingDirectory": "$(OutDir)"}]]
            pr.append(build_target)

            clean_target = ["Target", {"Name": "Clean"},
                            ["Exec", {"Command": self.directory_lock_path + " . ninja.exe -t clean " +  build_target_name,
                            "WorkingDirectory": "$(OutDir)"}]]
            pr.append(clean_target)

            compile_target = ["Target", {"Name": "ClCompile", "DependsOnTargets": "SelectClCompile"},
                            # SelectCLCompile leaves precompiled header creation in, but we can skip it - ninja will take care of that
                            ["Exec", {"Condition": "'%(ClCompile.PrecompiledHeader)' != 'Create' and '%(ClCompile.ExcludedFromBuild)'!='true' and '%(ClCompile.CompilerIteration)' == '' and @(ClCompile) != ''",
                                    "Command": self.directory_lock_path + " . ninja.exe %(ClCompile.OutputFile)",
                                    "WorkingDirectory": "$(OutDir)"}]]
            pr.append(compile_target)

        else: # empty targets for build project
            pr.append(["Target", {"Name": "Build"}])
            pr.append(["Target", {"Name": "Clean"}])
            pr.append(["Target", {"Name": "ClCompile"}])

        project_file_path = self.project_definition.get_absolute_path(self._project_file_path(target))
        if not os.path.exists(posixpath.dirname(project_file_path)):
            os.mkdir(posixpath.dirname(project_file_path))

        easy_xml.write_xml_if_changed(pr, project_file_path, pretty=True)

        # filters
        filters_project = ["Project", {"ToolsVersion": "4.0",
                                       "xmlns": "http://schemas.microsoft.com/developer/msbuild/2003"},
                           filter_group_files, filter_group_filters]
        easy_xml.write_xml_if_changed(filters_project, project_file_path + ".filters", pretty=True)


    def _write_solution(self, targets):

        def is_target_dependency(target, dependency):
            if dependency.name in target.deps: # direct dependency
                return True
            for dep in target.deps: # or indirect dependency of one of our depenencies
                t = self.project_definition.targets[dep]
                if is_target_dependency(t, dependency):
                    return True
            return False

        def project_solution_folder_path(target):
            source_dir = target.get_source_dir()

            # Disabled for now because solution folders are ordered before projects
            # resulting in confusing order
            if False:
                # if no other projects are in the folder we can remove last segment
                # otherwise there would be redundant segment in path (i.e. third_party/modp_b64/modp_b64)
                alone = True
                for target2 in targets:
                    if target2 != target and target2.get_source_dir().startswith(source_dir):
                        alone = False
                        break

                # only one project in the folder and name matches last path segment
                if alone and source_dir.endswith("/" + target.get_base_name() + "/"):
                    source_dir = posixpath.join(source_dir, "..")

            # normalize path, this will also remove trailing segment
            source_dir = posixpath.normpath(source_dir)

            source_dir = source_dir[2:]
            return source_dir

        class SolutionFolder:

            def __init__(self, name, path, parent):
                self.name = name
                self.path = path
                self.parent = parent
                self.uuid = uuid.uuid5(uuid.UUID('53acf19b-cba3-5019-90fa-640c295a343e'), str(self.path))

        output = StringIO()
        output.write("Microsoft Visual Studio Solution File, Format Version 12.00\n")
        output.write("# Visual Studio " + self.tool_version[:self.tool_version.find(".")] + "\n")

        # path to folder
        solution_folders = {}

        # target to solution folder
        target_to_folder = {}

        def get_solution_folder(solution_folder_path):
            if len(solution_folder_path) == 0:
                return None
            elif solution_folder_path in solution_folders:
                return solution_folders[solution_folder_path]
            else:
                parent, name = posixpath.split(solution_folder_path)
                res = SolutionFolder(name, solution_folder_path, get_solution_folder(parent))
                solution_folders[solution_folder_path] = res
                return res

        for target in targets:

            solution_folder_path = project_solution_folder_path(target)
            solution_folder = get_solution_folder(solution_folder_path)
            if solution_folder is not None:
                target_to_folder[target] = solution_folder

            output.write('Project("{8BC9CEB8-8B4A-11D0-8D11-00A0C91BC942}") = "' + target.get_base_name() + '", "' +
                          self.project_definition.get_relative_path(self._project_file_path(target)) + '", "{' +
                          str(self._project_uuid(target)) + '}"\n');
            # for now ignore project dependencies, it doesn't seem to help much given that ninja build takes care of that
            # output.write("\tProjectSection(ProjectDependencies) = postProject\n");
            # for t in targets:
            #     if t != target and is_target_dependency(target, t):
            #         uuid = str(self.project_uuid(t))
            #         output.write("\t\t{" + uuid + "} = {" + uuid + "}\n")
            # output.write("\tEndProjectSection\n");
            output.write("EndProject\n")

        # Print project definitions for solution folders
        for path, item in solution_folders.items():
            project_type = "2150E333-8FDC-42A3-9474-1A3956D46DE8";
            output.write('Project("{2150E333-8FDC-42A3-9474-1A3956D46DE8}") = "' + item.name + '", "' +
                         item.name + '", "{' + str(item.uuid) + '}"\n');
            output.write("EndProject\n")

        output.write("Global\n")

        config = self.configuration_name + "|" + self._get_platform();

        output.write("\tGlobalSection(SolutionConfigurationPlatforms) = preSolution\n")
        output.write("\t\t" + config + " = " + config  + "\n")
        output.write("\tEndGlobalSection\n")

        output.write("\tGlobalSection(ProjectConfigurationPlatforms) = postSolution\n")
        for target in targets:
            prefix = "{" + str(self._project_uuid(target)) + "}." + config
            output.write("\t\t" + prefix + ".ActiveCFG = " + config + "\n")
            output.write("\t\t" + prefix + ".Build.0 = " + config + "\n")
        output.write("\tEndGlobalSection\n")

        output.write("\tGlobalSection(SolutionProperties) = preSolution\n")
        output.write("\t\tHideSolutionNode = FALSE\n")
        output.write("\tEndGlobalSection\n")

        output.write("\tGlobalSection(NestedProjects) = preSolution\n");
        for path, folder in solution_folders.items():
            if not folder.parent is None:
                output.write("\t\t{" + str(folder.uuid) + "} = {" + str(folder.parent.uuid) + "}\n")
        for target, folder in target_to_folder.items():
            output.write("\t\t{" + str(self._project_uuid(target)) + "} = {" + str(folder.uuid) + "}\n")
        output.write("\tEndGlobalSection\n")

        output.write("EndGlobal\n")

        solution_file = self.project_definition.get_absolute_build_path() + self.solution_name + ".sln"
        overwrite_file_if_different(solution_file, output.getvalue())

        output.close()
