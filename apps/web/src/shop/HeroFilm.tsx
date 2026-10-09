// The home page's film (ADR-108): our own cover, path-traced from our own data, as a short
// silent loop. AV1 where the browser plays it, H.264 otherwise; the poster shows at once and
// stays for visitors who asked their device for less motion, who save data, or whose device
// will not start the film (iOS in Low Power Mode). The film plays only while it is on screen.
import { useEffect, useMemo, useRef, useState } from "react";
import "./hero-film.css";

export interface HeroMedia {
  /** H.264 (mp4): plays everywhere */
  h264?: string;
  /** AV1 (mp4): smaller and sharper, where the browser plays it */
  av1?: string;
  /** the first frame (jpg or webp) */
  poster?: string;
}

/** codec strings: AV1 main profile level 4.0, 8 bit; H.264 high profile level 4.1 */
const AV1 = 'video/mp4; codecs="av01.0.08M.08"';
const H264 = 'video/mp4; codecs="avc1.640029"';

function stillOnly(): boolean {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches)
    return true;
  const c = (
    navigator as Navigator & {
      connection?: { saveData?: boolean; effectiveType?: string };
    }
  ).connection;
  return Boolean(c?.saveData || /(^|-)2g$/.test(c?.effectiveType || ""));
}

export function HeroFilm({
  media,
  className = "",
}: {
  media: HeroMedia;
  className?: string;
}) {
  const film = Boolean(media.h264 || media.av1);
  const calm = useMemo(stillOnly, []);
  const [still, setStill] = useState(calm || !film);
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const v = ref.current;
    if (still || !v) return;
    // iOS plays inline only when muted is set before play (React sets the property late)
    v.muted = true;
    v.defaultMuted = true;
    const play = () => {
      if (document.hidden) return;
      v.play().catch(() => setStill(true)); // refused (Low Power Mode): the poster stays
    };
    let seen = true;
    const io = new IntersectionObserver(
      ([e]) => {
        seen = e.isIntersecting;
        if (seen) play();
        else v.pause();
      },
      { threshold: 0.01 },
    );
    io.observe(v);
    const visible = () => (document.hidden || !seen ? v.pause() : play());
    document.addEventListener("visibilitychange", visible);
    return () => {
      io.disconnect();
      document.removeEventListener("visibilitychange", visible);
    };
  }, [still]);

  if (still)
    return media.poster ? (
      <img className={`hf ${className}`} src={media.poster} alt="" />
    ) : (
      <div className={`hf hf-empty ${className}`} />
    );
  return (
    <video
      ref={ref}
      className={`hf ${className}`}
      poster={media.poster || undefined}
      muted
      autoPlay
      loop
      playsInline
      preload="auto"
      disablePictureInPicture
      disableRemotePlayback
      aria-hidden
      tabIndex={-1}
    >
      {media.av1 && <source src={media.av1} type={AV1} />}
      {media.h264 && <source src={media.h264} type={H264} />}
    </video>
  );
}
