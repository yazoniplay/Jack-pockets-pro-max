import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import type { DocumentaryProps, Scene } from "./types";

const mediaSource = (src: string) =>
  src.startsWith("https://") || src.startsWith("http://") ? src : staticFile(src);

const SceneFrame: React.FC<{ scene: Scene }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 12, scene.durationInFrames - 12, scene.durationInFrames], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const lift = interpolate(frame, [0, 24], [28, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#08090d", opacity }}>
      {scene.mediaSrc && scene.mediaType === "video" ? (
        <OffthreadVideo
          src={mediaSource(scene.mediaSrc)}
          muted
          loop
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : scene.mediaSrc ? (
        <Img
          src={mediaSource(scene.mediaSrc)}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : null}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(90deg, rgba(5,7,12,.94) 0%, rgba(5,7,12,.68) 52%, rgba(5,7,12,.16) 100%), linear-gradient(0deg, rgba(5,7,12,.6), transparent 55%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 112,
          right: 112,
          bottom: 176,
          transform: `translateY(${lift}px)`,
          opacity,
          color: "#f5f2eb",
          fontFamily: "Arial, Helvetica, sans-serif",
        }}
      >
        {scene.eyebrow ? (
          <div style={{ color: "#b7a17a", fontSize: 20, letterSpacing: 6, textTransform: "uppercase", marginBottom: 28 }}>
            {scene.eyebrow}
          </div>
        ) : null}
        <div style={{ fontSize: scene.kind === "title" ? 76 : 64, lineHeight: 1.08, fontWeight: 700, maxWidth: 1320 }}>
          {scene.title}
        </div>
        {scene.body ? (
          <div style={{ color: "rgba(245,242,235,.78)", fontSize: 28, lineHeight: 1.45, marginTop: 28, maxWidth: 1080 }}>
            {scene.body}
          </div>
        ) : null}
      </div>
      <div style={{ position: "absolute", left: 112, right: 112, top: 64, height: 2, background: "rgba(255,255,255,.24)" }} />
      <div style={{ position: "absolute", left: 112, bottom: 64, color: "rgba(255,255,255,.58)", fontSize: 16, letterSpacing: 3, textTransform: "uppercase" }}>
        JACK POCKETS PRO MAX
      </div>
    </AbsoluteFill>
  );
};

const CaptionFrame: React.FC<{ text: string }> = ({ text }) => (
  <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 86, pointerEvents: "none" }}>
    <div
      style={{
        maxWidth: "78%",
        padding: "12px 22px",
        backgroundColor: "rgba(4,5,8,.78)",
        color: "#fff",
        fontFamily: "Arial, Helvetica, sans-serif",
        fontSize: 28,
        fontWeight: 600,
        lineHeight: 1.35,
        textAlign: "center",
        borderRadius: 8,
        textShadow: "0 2px 8px rgba(0,0,0,.7)",
      }}
    >
      {text}
    </div>
  </AbsoluteFill>
);

export const Documentary: React.FC<DocumentaryProps> = (props) => {
  let cursor = 0;
  const sceneSequences = props.scenes.map((scene) => {
    const from = cursor;
    cursor += scene.durationInFrames;
    return (
      <Sequence key={scene.id} from={from} durationInFrames={scene.durationInFrames}>
        <SceneFrame scene={scene} />
      </Sequence>
    );
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#08090d" }}>
      {sceneSequences}
      {props.narrationSrc ? <Audio src={mediaSource(props.narrationSrc)} /> : null}
      {props.musicSrc ? <Audio src={mediaSource(props.musicSrc)} volume={0.12} /> : null}
      {props.captions.map((caption, index) => (
        <Sequence
          key={`${caption.startFrame}-${index}`}
          from={caption.startFrame}
          durationInFrames={Math.max(1, caption.endFrame - caption.startFrame)}
        >
          <CaptionFrame text={caption.text} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
