import React from "react";
import { Composition } from "remotion";
import { Documentary } from "./Documentary";
import type { DocumentaryProps } from "./types";

const defaultProps: DocumentaryProps = {
  title: "The Shape of History",
  subtitle: "A documentary",
  scenes: [
    {
      id: "opening",
      kind: "title",
      durationInFrames: 180,
      eyebrow: "A JACK POCKETS DOCUMENTARY",
      title: "The Shape of History",
      body: "A sample composition. Replace this scene plan with an approved documentary timeline.",
    },
    {
      id: "chapter-one",
      kind: "chapter",
      durationInFrames: 240,
      eyebrow: "CHAPTER 01",
      title: "Every story begins with a question.",
      body: "The renderer turns a structured scene manifest into a timed documentary sequence.",
    },
  ],
  captions: [
    { startFrame: 35, endFrame: 105, text: "A sample subtitle demonstrates timed captions." },
  ],
};

export const Root: React.FC = () => (
  <Composition
    id="Documentary"
    component={Documentary}
    durationInFrames={420}
    fps={30}
    width={1920}
    height={1080}
    defaultProps={defaultProps}
    calculateMetadata={({ props }) => ({
      durationInFrames: Math.max(
        1,
        props.scenes.reduce((total, scene) => total + scene.durationInFrames, 0),
      ),
    })}
  />
);
