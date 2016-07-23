This repository contains experimental project generators for GN

### dist/xcode.py

Generates Xcode project from JSON file. Unlike original GN Xcode generator this one generates separate indexing target for each GN target, which means include directories, defines and precompiled headers should be set properly for every indexed source file.

It also uses Custom build tool for Product targets, so that Clean action from IDE should work as expected.

Usage: `gn gen --ide=json --json-ide-script=<path-to>xcode.py out-dir`

### dist/msvc2015.py

Generates MSVC solution from JSON file. Uses CLCompile items for C/C++ files so that C files are properly indexed as C (they are indexed as C++ when being a custom build tool type resulting in false errors). Supports building single files (ctrl + F7), and PCH for intellisense.

Also synchronizes ninja invocations from MSVC on build folder, so that when visual studio tries building projects in parallel only one ninja instance is active at a time. 

Should work with both python 2.7 and 3.

Usage: `gn gen --ide=json --json-ide-script=<path-to>msvc2015.py out-dir`
