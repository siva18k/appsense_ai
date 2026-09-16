import { useEffect, useState } from "react";
import { BrandMark } from "./BrandMark";

function Arrow() {
  return (
    <span className="flow-arrow" aria-hidden>
      →
    </span>
  );
}

function Flow({ items }: { items: string[] }) {
  return (
    <div className="flow-row">
      {items.map((item, i) => (
        <span key={item} className="flow-bits">
          {i > 0 && <Arrow />}
          <span className="flow-node">{item}</span>
        </span>
      ))}
    </div>
  );
}

const SLIDES = [
  {
    kicker: "AppSense",
    title: "The application that keeps learning with you",
    body: "A self-learning companion for the teams who build, run, and evolve software — so the product is understood even when people change.",
    visual: "hero" as const,
  },
  {
    kicker: "The problem",
    title: "Knowledge walks out with people",
    body: "Traditional support hangs on a few SMEs. When they leave, the map of the application leaves with them.",
    visual: "problem" as const,
  },
  {
    kicker: "The key",
    title: "Knowledge remains. Always available.",
    body: "AppSense holds what the application is, how it runs, and how it fails — in one place, for every team, at any hour.",
    highlight: "No dependency on an individual SME. If someone leaves tomorrow, the next person can still learn, diagnose, and move the product forward.",
    visual: "stays" as const,
  },
  {
    kicker: "How it learns",
    title: "It adopts the app instead of waiting for a handbook",
    body: "Link the code, drop in notes, scan the repo, and chat. The picture of the system keeps adapting as the application changes.",
    visual: "learns" as const,
  },
  {
    kicker: "Who it serves",
    title: "One companion across the product lifecycle",
    body: "Everyone who touches the application learns from the same living source of truth — without a knowledge-transfer meeting.",
    visual: "teams" as const,
  },
  {
    kicker: "Day to day",
    title: "Maintain today. Enhance tomorrow.",
    body: "The same memory that walks an incident also informs the next change. Learning the app is continuous, not a one-time KT session.",
    visual: "dual" as const,
  },
  {
    kicker: "Effortless action",
    title: "Help without writing a KB for every step",
    body: "You do not have to author a perfect wiki or preset every action. Describe a skill when useful — AppSense guides resolution from what it already knows.",
    visual: "effortless" as const,
  },
  {
    kicker: "Control",
    title: "Human in the loop. Always.",
    body: "AppSense may propose the next step. Allowlisted commands run only after a person confirms. You keep judgment; it keeps the memory.",
    visual: "human" as const,
  },
];

function Visual({ kind }: { kind: (typeof SLIDES)[number]["visual"] }) {
  if (kind === "hero") {
    return (
      <figure className="deck-figure">
        <img src="/about/appsense-hero.png" alt="Living knowledge at the center of an application" />
        <figcaption>Code, notes, and operations orbit one living core.</figcaption>
      </figure>
    );
  }
  if (kind === "problem") {
    return (
      <div className="deck-compare">
        <article className="deck-panel warn">
          <p className="deck-panel-kicker">Today</p>
          <h3>SME bottleneck</h3>
          <Flow items={["Incident", "Find the expert", "Wait", "Hope they remember"]} />
          <p>Knowledge is trapped in people. KT fades. Tickets stall.</p>
        </article>
        <article className="deck-panel ok">
          <p className="deck-panel-kicker">With AppSense</p>
          <h3>Shared memory</h3>
          <Flow items={["Incident", "Ask the app", "Guided steps", "Human confirms"]} />
          <p>The system still knows — even when the SME is gone.</p>
        </article>
      </div>
    );
  }
  if (kind === "stays") {
    return (
      <figure className="deck-figure">
        <img src="/about/appsense-stays.png" alt="Knowledge archive that remains as people come and go" />
        <figcaption>People rotate. The knowledge stays in the hall.</figcaption>
      </figure>
    );
  }
  if (kind === "learns") {
    return (
      <div className="deck-visual-stack">
        <figure className="deck-figure compact">
          <img src="/about/appsense-loop.png" alt="Learning loop around a knowledge core" />
        </figure>
        <Flow items={["Code Base", "Scan", "Knowledge", "Skills", "Chat"]} />
        <div className="deck-mini-grid">
          <span>Scan writes the handbook</span>
          <span>Notes stay searchable</span>
          <span>Skills capture how work is done</span>
        </div>
      </div>
    );
  }
  if (kind === "teams") {
    return (
      <div className="deck-cards diagram">
        <article>
          <div className="role-mark">TS</div>
          <h3>Tech support</h3>
          <p>Incidents, logs, and steps from the live system — not a stale comment.</p>
        </article>
        <article>
          <div className="role-mark">DV</div>
          <h3>Developers</h3>
          <p>How it is wired, how to run it, what breaks before you change it.</p>
        </article>
        <article>
          <div className="role-mark">PO</div>
          <h3>Product owners</h3>
          <p>Capabilities and constraints without waiting for a walkthrough.</p>
        </article>
        <article>
          <div className="role-mark">OT</div>
          <h3>Ops, QA, partners</h3>
          <p>The same living knowledge, so handoffs do not reset the story.</p>
        </article>
      </div>
    );
  }
  if (kind === "dual") {
    return (
      <div className="deck-compare">
        <article className="deck-panel">
          <p className="deck-panel-kicker">Maintain</p>
          <h3>Keep the lights on</h3>
          <Flow items={["Symptom", "Logs + scan", "Step by step", "Confirm"]} />
          <p>Restarts, batches, and failures with the real run path.</p>
        </article>
        <article className="deck-panel">
          <p className="deck-panel-kicker">Enhance</p>
          <h3>Change with context</h3>
          <Flow items={["Idea", "How it works", "Risk", "Ship informed"]} />
          <p>The same memory informs the next improvement.</p>
        </article>
      </div>
    );
  }
  if (kind === "effortless") {
    return (
      <div className="deck-compare">
        <article className="deck-panel warn">
          <p className="deck-panel-kicker">Heavy model</p>
          <h3>Write every KB first</h3>
          <ul>
            <li>Wiki pages go stale</li>
            <li>Every action must be preset</li>
            <li>Work waits on documentation</li>
          </ul>
        </article>
        <article className="deck-panel ok">
          <p className="deck-panel-kicker">AppSense</p>
          <h3>Guide from what exists</h3>
          <ul>
            <li>Code, notes, and scans already in place</li>
            <li>Skills only when you want them</li>
            <li>Step-by-step help without a doc project</li>
          </ul>
        </article>
      </div>
    );
  }
  return (
    <div className="deck-visual-stack">
      <figure className="deck-figure compact">
        <img src="/about/appsense-human.png" alt="A person confirming an action before it reaches production" />
      </figure>
      <Flow items={["Propose", "You review", "Confirm", "Then it runs"]} />
    </div>
  );
}

export function AboutPresentation() {
  const [index, setIndex] = useState(0);
  const slide = SLIDES[index];
  const last = index === SLIDES.length - 1;

  function closeTab() {
    window.close();
  }

  useEffect(() => {
    document.title = "About AppSense";
    return () => {
      document.title = "AppSense";
    };
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") closeTab();
      if (e.key === "ArrowRight" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setIndex((i) => Math.min(SLIDES.length - 1, i + 1));
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        setIndex((i) => Math.max(0, i - 1));
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const split = slide.visual === "hero" || slide.visual === "stays" || slide.visual === "learns" || slide.visual === "human";

  return (
    <div className="deck" role="dialog" aria-modal="true" aria-label="About AppSense">
      <div className="deck-stage wide">
        <header className="deck-top">
          <div className="deck-brand">
            <BrandMark size={26} className="deck-mark" />
            <span className="brand-app">App</span><span className="brand-sense">Sense</span>{" "}
            <span className="brand-ai">ai</span>
          </div>
          <span className="deck-count">
            {index + 1} / {SLIDES.length}
          </span>
          <button type="button" className="deck-close" onClick={closeTab}>
            Close
          </button>
        </header>

        <div className={`deck-slide ${split ? "split" : "stack"}`} key={index}>
          <div className="deck-copy">
            <p className="deck-kicker">{slide.kicker}</p>
            <h2>{slide.title}</h2>
            <p className="deck-body">{slide.body}</p>
            {"highlight" in slide && slide.highlight && <p className="deck-highlight">{slide.highlight}</p>}
          </div>
          <div className="deck-visual">
            <Visual kind={slide.visual} />
          </div>
        </div>

        <footer className="deck-nav">
          <button type="button" className="deck-ghost" disabled={index === 0} onClick={() => setIndex(index - 1)}>
            Back
          </button>
          <div className="deck-dots">
            {SLIDES.map((s, i) => (
              <button
                key={s.title}
                type="button"
                className={i === index ? "on" : ""}
                aria-label={`Slide ${i + 1}`}
                onClick={() => setIndex(i)}
              />
            ))}
          </div>
          {last ? (
            <button type="button" className="primary" onClick={closeTab}>
              Get started
            </button>
          ) : (
            <button type="button" className="primary" onClick={() => setIndex(index + 1)}>
              Next
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
