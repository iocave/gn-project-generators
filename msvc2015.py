#!
import json
from impl.msvc import ProjectGenerator
from impl.common import *
import sys

def run():

    if len(sys.argv) != 2 and len(sys.argv) != 3:
        print("Usage: " + sys.argv[0] + " <path-to-json-file> [Solution-name]")
        exit(1)
    
    path_to_file = sys.argv[1]
    solution_name = "Solution" 
    if len(sys.argv) == 3:
        solution_name = sys.argv[2]
    
    with open(path_to_file, "r") as json_file:
        v = json_file.read()
        json_file.close()
        js = json.loads(v)
        
        project = Project(js)
            
        generator = ProjectGenerator(project, solution_name, tools_version = "14.0", platform_toolset = "v140")
        count = generator.generate()

        print("Done generating " + str(count) + " project file(s)") 

run()