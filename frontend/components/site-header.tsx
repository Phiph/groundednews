"use client";
import Link from "next/link";
import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { Moon, Search, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Home" },
  { href: "/blindspot", label: "Blindspot" },
  { href: "/sources", label: "Sources" },
  { href: "/admin", label: "Admin" },
];

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label="Toggle light or dark theme"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
    >
      {/* Both icons render; CSS picks one, so server and client markup match */}
      <Sun className="hidden dark:block" />
      <Moon className="dark:hidden" />
    </Button>
  );
}

/** Header search: a box on wider screens, an icon linking to /search on phones. Hidden on /search itself. */
function HeaderSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");
  return (
    <>
      <form
        role="search"
        className="relative hidden md:block"
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim()) router.push(`/search?q=${encodeURIComponent(q.trim())}`);
          setQ("");
        }}
      >
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search stories"
          aria-label="Search stories"
          className="h-8 w-52 pl-8 lg:w-64"
        />
      </form>
      <Button asChild variant="ghost" size="icon" className="md:hidden">
        <Link href="/search" aria-label="Search stories">
          <Search />
        </Link>
      </Button>
    </>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4 sm:gap-6">
        {/* On the narrowest phones the "Home" nav link stands in for the logo */}
        <Link href="/" aria-label="GroundedNews home" className="flex items-center gap-2 font-heading text-lg font-bold tracking-tight max-[379px]:hidden">
          {/* Mark: the three coverage colours */}
          <span aria-hidden className="flex h-4 w-5 overflow-hidden rounded-sm">
            <span className="flex-1 bg-bias-left" />
            <span className="flex-1 bg-bias-center" />
            <span className="flex-1 bg-bias-right" />
          </span>
          {/* Wordmark drops on very narrow screens so the nav fits */}
          <span className="hidden min-[440px]:inline">GroundedNews</span>
        </Link>
        <nav className="flex items-center gap-0.5 text-sm sm:gap-1">
          {NAV.map((n) => {
            // "/sources" also covers the singular "/source/[id]" profile pages
            const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href.replace(/s$/, ""));
            return (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-md px-1.5 py-1.5 font-medium sm:px-2.5 text-muted-foreground transition-colors hover:text-foreground",
                  active && "bg-muted text-foreground"
                )}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center sm:gap-1">
          {pathname !== "/search" && <HeaderSearch />}
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
