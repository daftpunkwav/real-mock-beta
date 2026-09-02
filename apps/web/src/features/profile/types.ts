import type { UserProfileResponse as UserProfile } from "@/lib/api/contract";
import type { RequiredKey } from "./profileRules";

/** 局部更新档案的补丁函数:命中必填键时同时清除对应缺失标记 */
export type ProfilePatch = <K extends keyof UserProfile>(
  key: K,
  value: UserProfile[K],
) => void;

/** 各表单区块的共享 props:数据 + 补丁 + 必填错误标记 */
export interface ProfileSectionProps {
  profile: UserProfile;
  patch: ProfilePatch;
  requiredError: (key: RequiredKey) => boolean;
}
