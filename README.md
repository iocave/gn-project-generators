This repository contains custom project generators for GN

### gen_xcode.py

Generates Xcode project from JSON file. Unlike original GN Xcode generator this one generates separate indexing target for each GN target, which means include include directories, defines and precompiled headers should be set properly for every indexed source file.

It also uses Custom build tool for Product targets, so that Clean action from IDE should work as expected.

Usage: `gn gen --ide=json --exec-script=<path-to>gen_xcode.py out-dir`
