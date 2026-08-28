/** 去掉标点空白，用于回采相似度判断。 */
export function normalizeEchoText(s: string): string {
  return s
    .replace(/[\s\*\#`~，。！？、,.!?;:：；""''\-—…（）()【】\[\]]/g, "")
    .toLowerCase();
}

/** 候选人文本是否高度像上一句面试官发言（扬声器回采）。 */
export function isLikelyEchoOfAssistant(userText: string, assistantText: string): boolean {
  const u = normalizeEchoText(userText);
  const a = normalizeEchoText(assistantText);
  if (u.length < 12 || a.length < 12) return false;
  if (u.includes(a.slice(0, Math.min(40, a.length))) || a.includes(u.slice(0, Math.min(40, u.length)))) {
    return true;
  }
  const window = Math.min(u.length, a.length, 80);
  let hit = 0;
  for (let i = 0; i < window; i++) {
    if (u[i] === a[i]) hit += 1;
  }
  if (hit / window >= 0.55) return true;
  const probe = u.slice(0, Math.min(24, u.length));
  if (probe.length >= 12 && a.includes(probe)) return true;
  return false;
}
