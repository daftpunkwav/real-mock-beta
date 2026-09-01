/** 3D 通道实例句柄类型（@met4citizen/talkinghead 的极小子集，供 boot/gaze/emotion/mouth 共用）。 */

export type HeadInstance = {
  showAvatar: (avatar: Record<string, unknown>, onprogress?: (ev: unknown) => void) => Promise<void>;
  setMood: (mood: string) => void;
  setValue: (mt: string, val: number, ms?: number | null) => void;
  setBaselineValue?: (mt: string, val: number | null) => void;
  setFixedValue?: (mt: string, val: number | null, ms?: number | null) => void;
  getMoodNames?: () => string[];
  lookAt?: (x: number, y: number, t: number) => void;
  lookAtCamera?: (t: number) => void;
  makeEyeContact?: (t: number) => void;
  stop?: () => void;
};
