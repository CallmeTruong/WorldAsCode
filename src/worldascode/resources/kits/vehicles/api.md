## Vehicle parts (frames from `b.at(x, z, yaw)`; local +X is forward, wheels stand on y = 0)

- `b.car(frame, {form: 'sedan' | 'hatch' | 'suv', length, width, height, material, glass, wheelMaterial})`.
- `b.van(frame, {length, width, height, material, glass, wheelMaterial})`, `b.bus(frame, {length = 12, width, height, material, glass, wheelMaterial})`.
- `b.truck(frame, {length = 8, width, height, material, bodyMaterial, glass, wheelMaterial})`, `b.tram(frame, {length = 14, width, height, material, glass, wheelMaterial})`, `b.bicycle(frame, {material, wheelMaterial})`.
