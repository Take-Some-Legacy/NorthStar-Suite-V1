# North Star NEMAT Packer

First-party material library tool for `.nemat` NEF8 material_library assets.

## Usage

```bat
tools\toolbelt\first_party\northstar\nemat_packer\bin\northstar-nemat-packer.exe create-draft -o materials\skin.nemat.xml
tools\toolbelt\first_party\northstar\nemat_packer\bin\northstar-nemat-packer.exe pack -i materials\skin.nemat.xml -o assets\materials\skin.nemat
tools\toolbelt\first_party\northstar\nemat_packer\bin\northstar-nemat-packer.exe inspect -i assets\materials\skin.nemat
tools\toolbelt\first_party\northstar\nemat_packer\bin\northstar-nemat-packer.exe validate -i assets\materials\skin.nemat
```

Source stays in `tools/toolsSrc/nemat_packer`; execute-ready payload and descriptor live here in `toolbelt`.
