# CAD Files

This folder contains all mechanical and hardware design files for the **DynaBraille** project.

## Folder Structure (suggested)

```
cad/
├── enclosure/        # 3D-printable enclosure parts
├── pcb/              # PCB layouts and schematics
├── assembly/         # Full assembly files
└── exports/          # Exported formats (STL, DXF, STEP, Gerber)
```

## Supported File Types

| Format | Tool | Purpose |
|--------|------|---------|
| `.f3d` | Autodesk Fusion 360 | Native editable design files |
| `.step` / `.stp` | Any CAD tool | Universal exchange format |
| `.stl` | Slicer (e.g. Cura) | 3D printing |
| `.dxf` | Any CAD / laser cutter | 2D profiles |
| `.kicad_pcb` | KiCad | PCB layout |
| `.sch` | KiCad / EasyEDA | Schematic |
| `.gerber` / `.gbr` | PCB manufacturers | Fabrication files |

## How to Contribute

1. Place your files in the appropriate subfolder above.
2. Use descriptive names — e.g., `top_cover_v2.stl` instead of `file1.stl`.
3. If you update an existing part, increment the version suffix (`_v2`, `_v3`).
4. For large binary files, consider using **Git LFS** (see below).

## Git LFS (Large File Storage)

CAD files can be large. If you have Git LFS installed, it is already configured
to track common CAD formats in this repo (see `.gitattributes`).

To install Git LFS:
```bash
# Ubuntu / Debian
sudo apt install git-lfs
git lfs install

# macOS
brew install git-lfs
git lfs install
```

## Contact

For questions about the hardware design, reach out to the hardware team lead.
