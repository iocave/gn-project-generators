This repository contains custom project generators for GN

### xcode.py

Generates Xcode project from JSON file. Unlike original GN Xcode generator this one generates separate indexing target for each GN target, which means include directories, defines and precompiled headers should be set properly for every indexed source file.

It also uses Custom build tool for Product targets, so that Clean action from IDE should work as expected.

Usage: `gn gen --ide=json --json-ide-script=<path-to>xcode.py out-dir`
