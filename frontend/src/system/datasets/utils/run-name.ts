/** 运行名形如「数据集/版本 · 模型」，对比视图里只展示模型名（数据集名面包屑已有，避免重复噪声）。 */
export const shortRunName = (name: string): string => {
  const parts = name.split('·');
  return parts[parts.length - 1]?.trim() || name;
};
