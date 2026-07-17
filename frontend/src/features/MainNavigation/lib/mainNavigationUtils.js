function normalizedRoutePath(value) {
  if (typeof value !== "string") return "";

  const route = value.trim();

  if (!route) return "";

  const pathname = route
    .split(/[?#]/, 1)[0]
    .replace(/\/+$/, "");

  return pathname || "/";
}

export function isMainNavigationItemActive(
  pathname,
  href,
) {
  const currentPath = normalizedRoutePath(pathname);
  const itemPath = normalizedRoutePath(href);

  if (!currentPath || !itemPath || itemPath === "/") {
    return currentPath === itemPath;
  }

  return currentPath === itemPath
    || currentPath.startsWith(`${itemPath}/`);
}
