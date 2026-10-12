/**
 * 设计系统图标层（规范：docs/架构/UI/设计系统.md 第 5 节）。
 *
 * 全部图标经 Tabler Icons 引入：MIT 许可证（Copyright (c) 2020-2026 Paweł Kuna，
 * 结论见前端工程规范第 2 节依赖登记），线性风格、24 网格、1.5px 描边、单色 currentColor，
 * 包声明 sideEffects: false，命名引入可 tree-shake。
 *
 * 尺寸约定：默认 16px（控件内）；侧轨/顶栏大按钮 20px；行内 caret 与表头指示 12px，
 * 例外在调用点显式传 size。描边宽度在本层锁定 1.5，调用点不传 stroke。
 * 新增图标必须在本文件登记；纯图标按钮必须配 aria-label 或 title（规范第 5 节）。
 */
import {
  IconArrowBackUp,
  IconArrowForwardUp,
  IconCheck,
  IconChevronDown,
  IconChevronRight,
  IconChevronUp,
  IconDeviceFloppy,
  IconPencil,
  IconPlayerPlay,
  IconPlus,
  IconRefresh,
  IconSettings,
  IconTrash,
  IconX,
} from "@tabler/icons-react";
import type { IconProps, TablerIcon } from "@tabler/icons-react";

export type { IconProps };

/** 预设默认参数：16px 控件尺寸 + 1.5px 描边；size/stroke 可被调用点覆盖（stroke 不推荐）。 */
function preset(Icon: TablerIcon, defaultSize = 16) {
  return function AppIcon({ size, stroke, ...rest }: IconProps) {
    return <Icon size={size ?? defaultSize} stroke={stroke ?? 1.5} {...rest} />;
  };
}

export const Undo = preset(IconArrowBackUp);
export const Redo = preset(IconArrowForwardUp);
export const Save = preset(IconDeviceFloppy);
export const Play = preset(IconPlayerPlay);
export const Settings = preset(IconSettings);
export const Refresh = preset(IconRefresh);
export const Close = preset(IconX);
export const Plus = preset(IconPlus);
export const Check = preset(IconCheck);
export const Pencil = preset(IconPencil);
export const Trash = preset(IconTrash);
export const ChevronUp = preset(IconChevronUp);
export const ChevronDown = preset(IconChevronDown);
export const ChevronRight = preset(IconChevronRight);
