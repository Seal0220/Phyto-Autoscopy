import crypto from "node:crypto";

export function passwordsMatch(
  supplied,
  configured,
) {
  const suppliedDigest = crypto
    .createHash("sha256")
    .update(String(supplied || ""), "utf8")
    .digest();
  const configuredDigest = crypto
    .createHash("sha256")
    .update(String(configured || ""), "utf8")
    .digest();
  return crypto.timingSafeEqual(suppliedDigest, configuredDigest);
}
