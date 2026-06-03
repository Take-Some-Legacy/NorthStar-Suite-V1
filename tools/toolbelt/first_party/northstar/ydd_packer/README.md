# North Star YDD Packer

Builds and inspects `.ydd` resident NEF8 ListFile drawable dictionaries.

`.ydd` stores multiple model entries addressed as `file.ydd@model_name`.

## Usage

```bat
tools\toolbelt\first_party\northstar\ydd_packer\bin\northstar-ydd-packer.exe pack -i body.obj -i head.glb -o assets\models\ped.ydd
tools\toolbelt\first_party\northstar\ydd_packer\bin\northstar-ydd-packer.exe list -i assets\models\ped.ydd
tools\toolbelt\first_party\northstar\ydd_packer\bin\northstar-ydd-packer.exe inspect -i assets\models\ped.ydd
tools\toolbelt\first_party\northstar\ydd_packer\bin\northstar-ydd-packer.exe validate -i assets\models\ped.ydd
```

Sources: OBJ, glTF, GLB. FBX is recognized and reserved for a dedicated importer-provider pass.
