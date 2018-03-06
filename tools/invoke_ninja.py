import sys
import os
from subprocess import call

target = sys.argv[1]
if target.startswith("//"):
    target = target[2:]

args = []

if os.path.isfile("ninja"):
    args += ["./ninja"]
else:
    args += ["ninja"]

action = None

if len(sys.argv) == 3:
    action = sys.argv[2]

def run():    

    global args
    global action
    
    if action is None:
        if target != "alltargets":
            args += [target]
    elif action == "clean":
        args += ["-t", "clean", target]
    else:
        message = "Don't know how to perform '" + action + "'"
        print(message)
        exit(1)

    exit(call(args))

try:
    run()
except KeyboardInterrupt:
    print("Build interrupted by Xcode")
    exit(0)
