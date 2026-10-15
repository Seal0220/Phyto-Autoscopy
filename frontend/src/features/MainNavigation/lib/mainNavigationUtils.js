import {
  ANALYSIS_SECONDARY_NAVIGATION_ITEMS,
  CAPTURE_SECONDARY_NAVIGATION_ITEMS,
} from "../mainNavigationConfig";

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

export function secondaryNavigationGroups(
  pathname,
  {
    canOpenResults = false,
    navigationLocked = false,
    resultsLocked = false,
  } = {},
) {
  const path = normalizedRoutePath(pathname);
  if (path === "/capture") {
    return [{ id: "capture", label: "捕捉頁面導覽", items: CAPTURE_SECONDARY_NAVIGATION_ITEMS }];
  }
  if (!isMainNavigationItemActive(path, "/analysis")) return [];
  const groups = [{
    id: "analysis",
    label: "分析頁面導覽",
    items: ANALYSIS_SECONDARY_NAVIGATION_ITEMS.map((item) => ({
      ...item,
      disabled: navigationLocked,
    })),
  }];
  if (path === "/analysis" || path === "/analysis/new") return groups;
  const match = path.match(/^\/analysis\/([^/]+)(?:\/(results|review))?$/);
  if (!match) return groups;
  const runPath = `/analysis/${match[1]}`;
  const resultsPage = match[2] === "results";
  groups.push({
    id: "analysis-record",
    label: "分析紀錄導覽",
    items: [
      { href: runPath, label: "分析紀錄", disabled: navigationLocked },
      {
        href: `${runPath}/results`,
        label: "分析結果",
        disabled: !resultsPage && (!canOpenResults || resultsLocked),
      },
    ],
  });
  return groups;
}

export function isSecondaryNavigationItemActive(
  pathname,
  href,
) {
  return !href.includes("#") && normalizedRoutePath(pathname) === normalizedRoutePath(href);
}
