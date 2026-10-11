export function isGenericITResume(item: {title?: string; target_position?: string}): boolean {
  const label = String(item.title || item.target_position || "")
    .normalize("NFKC")
    .trim()
    .toLocaleLowerCase("ru-RU")
    .replace(/[‐‑‒–—−]/g, "-")
    .replace(/\s*-\s*/g, "-");
  return label === "ит-специалист";
}
