export type Caption = {
  startFrame: number;
  endFrame: number;
  text: string;
};

export type Scene = {
  id: string;
  kind: "title" | "footage" | "chapter";
  durationInFrames: number;
  title: string;
  body?: string;
  mediaSrc?: string;
  mediaType?: "image" | "video";
  eyebrow?: string;
  sourceCredit?: string;
};

export type DocumentaryProps = {
  title: string;
  subtitle?: string;
  narrationSrc?: string;
  musicSrc?: string;
  scenes: Scene[];
  captions: Caption[];
};
