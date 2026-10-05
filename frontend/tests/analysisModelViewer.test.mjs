import test from "node:test";
import assert from "node:assert/strict";
import { PlyParser } from "@mkkellogg/gaussian-splats-3d";
import { Vector3 } from "three";

test("direct Gaussian parser preserves PLY row IDs, including transparent vertices", () => {
  const names = ["x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"];
  const header = Buffer.from(`ply\nformat binary_little_endian 1.0\nelement vertex 4\n${names.map((name) => `property float ${name}\n`).join("")}end_header\n`);
  const positions = [[100, 0, 2], [0, 3, 1], [-70, 1, 20], [1, -2, 5]];
  const values = new Float32Array(4 * names.length);
  for (let row = 0; row < 4; row += 1) {
    values.set([...positions[row], 0, 0, 0, row === 1 ? -80 : 1, -4, -4, -4, 1, 0, 0, 0], row * names.length);
  }
  const bytes = Buffer.concat([header, Buffer.from(values.buffer)]);
  const array = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const parsed = PlyParser.parseToUncompressedSplatBuffer(array, 1);
  assert.equal(parsed.getSplatCount(), 4);
  for (let row = 0; row < 4; row += 1) {
    const position = new Vector3();
    parsed.getSplatCenter(row, position);
    assert.deepEqual(position.toArray(), positions[row]);
  }
});
