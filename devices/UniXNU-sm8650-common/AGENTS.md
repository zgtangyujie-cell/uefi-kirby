# Agent instructions

This repository owns shared SM8650 resources and platform operations.
Keep board peripherals, firmware selection, partition layout, and power
policy in the device repository. Preserve runtime source filenames,
classes, symbols, bundle IDs, and protocol IDs.

Read these UniXNU pages before editing:

1. [Porting](https://unixnu.com/porting/)
2. [Device repositories](https://unixnu.com/porting/device-repository)
3. [Components](https://unixnu.com/reference/components)
4. [Device trees](https://unixnu.com/porting/device-tree)
5. [Driver matching](https://unixnu.com/drivers/device-tree-matching)

Read the selected component README, build interface, and relevant source
before adding a capability. Search `components.toml` in UniXNU for existing
implementations. Select by interface, hardware requirements, OS ABI, and
board dependencies.

For kernel work, read the selected OS profile, XNU source, and ordered
patches. For migration, read the
[migration guide](https://unixnu.com/porting/migration).

Run builds from the UniXNU checkout:

```sh
./unixnu defconfig sheng_defconfig --device ../UniXNU-sheng
./unixnu tree --device ../UniXNU-sheng
./unixnu build kernel --device ../UniXNU-sheng
```

Report commands, results, required local inputs, and hardware checkpoints.
Keep the documentation site in UniXNU. Write concise English describing
current behavior. Use direct statements and ordinary punctuation.
