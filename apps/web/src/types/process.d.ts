/** 最小 Node/process 类型，避免依赖 @types/node 解析问题。 */
declare namespace NodeJS {
  interface ProcessEnv {
    NODE_ENV?: "development" | "production" | "test";
    [key: string]: string | undefined;
  }
}

declare const process: {
  env: NodeJS.ProcessEnv;
};
