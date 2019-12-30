## Blender resources for The Dark Mod

### Export scripts

This repository contains the following scripts:

* `io_export_ase.py`: export script for ASE model format
* `io_export_lwo.py`: export script for LWO model format

To install the scripts, simply download them to a location of your choice, then
install them via the `Add-ons` section of Blender preferences. The new file
formats should appear under `Export` in the `File` menu.

**NOTE**: Make sure to download the scripts from the correct branch. The
blender-2.80 scripts will not work with Blender 2.79 and vice versa.

### Application template

In the Template directory is a zipped startup file which can be installed as a
separate application template (available from the splash screen or from the
**File -> New** submenu). This sets up an empty scene with certain settings that
are more appropriate for creating models for the Dark Mod, such as grid lines
every 8 units (rather than 10), and a far clip plane that is far enough away
not to clip objects that are several thousand units in size.

In order to install the template:

- From Blender's *Application menu* (click on the Blender icon at the top
  left), choose `Install Application Template...`
- Navigate and choose the `DarkMod.zip` archive.
- The template will now be installed (and copied into your own user profile
  directory), and there should now be an option `Dark Mod modelling` in the
  **File -> New** submenu).
