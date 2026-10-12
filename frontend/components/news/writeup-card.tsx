import Markdown, { type Components } from "react-markdown";
import { Sparkles } from "lucide-react";
import type { Writeup } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";

const HEADINGS: Record<Writeup["kind"], string> = {
  story: "The story so far",
  briefing: "The day in brief",
  thread: "Where things stand",
};

// Tailwind's reset strips list and heading styles, so restore the few Markdown needs.
// Only children/href are passed on: react-markdown also hands each component a `node` prop.
const heading: Components["h3"] = ({ children }) => <h3 className="font-heading font-semibold">{children}</h3>;
const ELEMENTS: Components = {
  p: ({ children }) => <p className="leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
  h1: heading,
  h2: heading,
  h3: heading,
  a: ({ href, children }) => (
    <a href={href} className="underline underline-offset-2" target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
};

/**
 * A story write-up, day's briefing or thread summary, written by Claude. Renders nothing
 * without one. Raw HTML in the Markdown is dropped; unsafe link URLs are stripped by react-markdown.
 */
export function WriteupCard({ writeup }: { writeup?: Writeup | null }) {
  if (!writeup) return null;
  const by = writeup.author === "session" ? "Written with Claude" : "Written by Claude";
  return (
    <Card>
      <CardContent className="space-y-3">
        <h2 className="font-heading font-semibold">{writeup.title || HEADINGS[writeup.kind]}</h2>
        <div className="space-y-3 text-sm">
          <Markdown skipHtml components={ELEMENTS}>
            {writeup.body}
          </Markdown>
        </div>
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <Sparkles className="mt-px size-3 shrink-0 opacity-70" aria-hidden />
          <span>
            {by} from the outlets&apos; headlines and summaries · updated {timeAgo(writeup.updated_at)}
            {writeup.stale &&
              ` · ${writeup.new_articles} new ${writeup.new_articles === 1 ? "article" : "articles"} since`}
          </span>
        </p>
      </CardContent>
    </Card>
  );
}
