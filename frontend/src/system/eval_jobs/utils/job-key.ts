/** 由任务显示名自动生成唯一任务标识（job_key）。
 *  ASCII slug + 随机后缀；中文/无 ASCII 名退回 job-<rand>。用户不再手填。 */
export const genJobKey = (name: string): string => {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 24);
  const rand = Math.random().toString(36).slice(2, 8);
  return slug ? `${slug}-${rand}` : `job-${rand}`;
};
