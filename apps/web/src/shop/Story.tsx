// The home page as one scrolling story (docs/plans/scroll-site.md, ADR-067), in the S2DIO house
// style. The film shrinks into the arch of the logo; then one pinned 3D scene in which scrolling
// morphs our own data (the furniture, the cover, its pieces, flat on the roll, sewn and fitted,
// the rain); then the workshop in arch-framed clips sliding sideways; true numbers; the FAQ.
// Smooth scrolling (Lenis) and scrubbed motion (GSAP ScrollTrigger); visitors who asked their
// device for less motion get the same story without the motion.
import { useEffect, useMemo, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";
import { StoryScene } from "./StoryScene";

gsap.registerPlugin(ScrollTrigger);

type T = Record<string, string>;
export interface StoryContent {
  chapters: { title: T; text: T }[];
  work: { title: T; items: { clip: string; title: T; text: T }[] };
  numbers: { title: T; items: { value: number; suffix: string; label: T }[] };
}

export function Story({
  t,
  hero,
  story,
  media,
  model,
  cta,
  configure,
  children,
}: {
  t: (x: T | undefined) => string;
  hero: { title: T; subtitle: T };
  story: StoryContent;
  media: Record<string, string>;
  model: string;
  cta: string;
  configure: string;
  children?: React.ReactNode;
}) {
  const calm = useMemo(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    [],
  );
  const root = useRef<HTMLDivElement>(null);
  const pinned = useRef<HTMLDivElement>(null);
  const progress = useRef(0);
  const [chapter, setChapter] = useState(0);

  // smooth scrolling, tied to ScrollTrigger
  useEffect(() => {
    if (calm) return;
    const lenis = new Lenis({ lerp: 0.09 });
    lenis.on("scroll", ScrollTrigger.update);
    const raf = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(raf);
    gsap.ticker.lagSmoothing(0);
    return () => {
      gsap.ticker.remove(raf);
      lenis.destroy();
    };
  }, [calm]);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const ctx = gsap.context(() => {
      // 1. the film shrinks into the arch
      gsap.fromTo(
        ".st-hero-frame",
        { clipPath: "inset(0% 0% 0% 0% round 0px 0px 0px 0px)" },
        {
          clipPath: "inset(10% 8% 8% 8% round 48vw 48vw 0px 0px)",
          ease: "none",
          scrollTrigger: {
            trigger: ".st-hero",
            start: "top top",
            end: "bottom top",
            scrub: true,
          },
        },
      );
      gsap.to(".st-hero-text", {
        yPercent: -40,
        opacity: 0,
        ease: "none",
        scrollTrigger: {
          trigger: ".st-hero",
          start: "top top",
          end: "60% top",
          scrub: true,
        },
      });
      // 2. the 3D chapters: scrolling through the tall section drives the scene
      ScrollTrigger.create({
        trigger: ".st-chapters",
        start: "top top",
        end: "bottom bottom",
        onUpdate: (s) => {
          progress.current = s.progress;
          setChapter(
            Math.min(
              story.chapters.length - 1,
              Math.floor(s.progress * story.chapters.length),
            ),
          );
        },
      });
      // 3. the workshop clips slide sideways while the section is pinned
      const track = el.querySelector<HTMLElement>(".st-track");
      if (track)
        gsap.to(track, {
          x: () => -(track.scrollWidth - window.innerWidth + 64),
          ease: "none",
          scrollTrigger: {
            trigger: ".st-work",
            start: "top top",
            end: () => `+=${track.scrollWidth}`,
            pin: true,
            scrub: true,
            invalidateOnRefresh: true,
          },
        });
      // 4. the numbers count up once
      el.querySelectorAll<HTMLElement>(".st-num").forEach((n) => {
        const to = Number(n.dataset.to);
        const o = { v: 0 };
        gsap.to(o, {
          v: to,
          duration: 1.6,
          ease: "power2.out",
          onUpdate: () => (n.textContent = Math.round(o.v).toLocaleString()),
          scrollTrigger: { trigger: n, start: "top 85%", once: true },
        });
      });
      // everything else rises softly into view
      gsap.utils.toArray<HTMLElement>(".st-rise").forEach((r) =>
        gsap.from(r, {
          y: 40,
          opacity: 0,
          duration: 1.1,
          ease: "power3.out",
          scrollTrigger: { trigger: r, start: "top 88%" },
        }),
      );
    }, el);
    return () => ctx.revert();
  }, [story.chapters.length]);

  const clip = (name: string) => media[name] || "";
  return (
    <div className="st" ref={root}>
      <section className="st-hero">
        <div className="st-hero-frame">
          {clip("hero") ? (
            <video
              src={clip("hero")}
              autoPlay={!calm}
              muted
              loop
              playsInline
              preload="auto"
            />
          ) : (
            <div className="st-hero-fallback" />
          )}
        </div>
        <div className="st-hero-text">
          <h1>{t(hero.title)}</h1>
          <p>{t(hero.subtitle)}</p>
          <a className="st-btn" href={configure}>
            {cta} →
          </a>
        </div>
        <span className="st-scroll" aria-hidden>
          ↓
        </span>
      </section>

      <section
        className="st-chapters"
        style={{ height: `${story.chapters.length * 110}vh` }}
      >
        <div className="st-pinned" ref={pinned}>
          <StoryScene model={model} progress={progress} />
          <ol className="st-captions">
            {story.chapters.map((c, i) => (
              <li key={i} className={i === chapter ? "on" : ""}>
                <span className="st-step">
                  {String(i + 1).padStart(2, "0")} /{" "}
                  {String(story.chapters.length).padStart(2, "0")}
                </span>
                <h2>{t(c.title)}</h2>
                <p>{t(c.text)}</p>
              </li>
            ))}
          </ol>
          {clip("rain") && (
            <div
              className={`st-rain ${chapter === story.chapters.length - 1 ? "on" : ""}`}
            >
              <video
                src={clip("rain")}
                autoPlay={!calm}
                muted
                loop
                playsInline
              />
            </div>
          )}
          <div className="st-bar">
            {story.chapters.map((_, i) => (
              <span key={i} className={i <= chapter ? "on" : ""} />
            ))}
          </div>
        </div>
      </section>

      <section className="st-work">
        <h2 className="st-work-title">{t(story.work.title)}</h2>
        <div className="st-track">
          {story.work.items.map((w) => (
            <figure key={w.clip} className="st-card">
              <div className="st-arch">
                {clip(w.clip) ? (
                  <video
                    src={clip(w.clip)}
                    autoPlay={!calm}
                    muted
                    loop
                    playsInline
                    preload="metadata"
                  />
                ) : (
                  <div className="st-arch-empty" />
                )}
              </div>
              <figcaption>
                <h3>{t(w.title)}</h3>
                <p>{t(w.text)}</p>
              </figcaption>
            </figure>
          ))}
        </div>
      </section>

      <section className="st-numbers">
        <h2 className="st-rise">{t(story.numbers.title)}</h2>
        <div className="st-grid">
          {story.numbers.items.map((n, i) => (
            <div key={i} className="st-figure st-rise">
              <strong>
                <span className="st-num" data-to={n.value}>
                  {calm ? n.value : 0}
                </span>
                {n.suffix && <small>{n.suffix.trim()}</small>}
              </strong>
              <span>{t(n.label)}</span>
            </div>
          ))}
        </div>
        <a className="st-btn dark st-rise" href={configure}>
          {cta} →
        </a>
      </section>
      {children}
    </div>
  );
}
