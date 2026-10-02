// "How Cover Studio works": docs/handbook/how-it-works.md, shown in the app at #/guide (also
// before logging in, for the people who get an invitation). One source: the handbook file.
import guide from "../../../docs/handbook/how-it-works.md?raw";

const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const inline = (s: string) =>
  esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>");

// the little Markdown the handbook uses: headings, numbered and dotted lists, paragraphs
function toHtml(md: string): string {
  const out: string[] = [];
  let list: "ol" | "ul" | null = null;
  let sub = false; // inside a dotted list within an item
  let para: string[] = [];
  const flushPara = () => {
    if (para.length) out.push(`<p>${inline(para.join(" "))}</p>`);
    para = [];
  };
  const closeSub = () => {
    if (sub) out.push("</li></ul>");
    sub = false;
  };
  const closeList = () => {
    closeSub();
    if (list) out.push(`</li></${list}>`);
    list = null;
  };
  for (const raw of md.split("\n")) {
    const line = raw.trimEnd();
    const item = line.match(/^(\d+\.|-)\s+(.*)$/);
    const subItem = list ? line.match(/^\s{2,}-\s+(.*)$/) : null;
    if (subItem) {
      out.push(sub ? "</li><li>" : "<ul><li>");
      sub = true;
      out.push(inline(subItem[1]));
    } else if (/^#{1,2}\s/.test(line)) {
      flushPara();
      closeList();
      const level = line.startsWith("## ") ? 2 : 1;
      out.push(`<h${level}>${inline(line.replace(/^#+\s/, ""))}</h${level}>`);
    } else if (item) {
      flushPara();
      closeSub();
      const kind = item[1] === "-" ? "ul" : "ol";
      if (list !== kind) {
        closeList();
        out.push(`<${kind}><li>`);
        list = kind;
      } else out.push("</li><li>");
      out.push(inline(item[2]));
    } else if (list && /^\s+\S/.test(line)) {
      out.push(" " + inline(line.trim())); // the item goes on
    } else if (line === "") {
      flushPara();
      closeList();
    } else {
      closeList();
      para.push(line);
    }
  }
  flushPara();
  closeList();
  return out.join("");
}

const HTML = toHtml(guide);

export default function Guide({ loggedIn }: { loggedIn: boolean }) {
  return (
    <article className="guide">
      {!loggedIn && (
        <p className="muted">
          <a href="#/">Log in to Cover Studio</a>
        </p>
      )}
      <div dangerouslySetInnerHTML={{ __html: HTML }} />
    </article>
  );
}
