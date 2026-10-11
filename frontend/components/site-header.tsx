"use client";
import Link from "next/link";
import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { Menu, Moon, Search, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Home" },
  { href: "/briefing", label: "Briefing" },
  { href: "/blindspot", label: "Blindspot" },
  { href: "/sources", label: "Sources" },
  { href: "/diet", label: "My diet" },
  { href: "/admin", label: "Admin" },
];

function isActive(href: string, pathname: string) {
  if (href === "/") return pathname === "/";
  // "/sources" also covers the singular "/source/[id]" profile pages
  return pathname.startsWith(href.replace(/s$/, ""));
}

/** Below lg the links don't fit beside search, so they move into a menu. */
function NavMenu({ pathname }: { pathname: string }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Open menu" className="lg:hidden">
          <Menu />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        {NAV.map((n) => (
          <DropdownMenuItem key={n.href} asChild>
            <Link
              href={n.href}
              aria-current={isActive(n.href, pathname) ? "page" : undefined}
              className={cn(isActive(n.href, pathname) && "font-semibold")}
            >
              {n.label}
            </Link>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

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
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
        <Link href="/" aria-label="GroundedNews home" className="flex items-center gap-2 font-heading text-lg font-bold tracking-tight">
          {/* Mark: the three coverage colours */}
          <span aria-hidden className="flex h-4 w-5 overflow-hidden rounded-sm">
            <span className="flex-1 bg-bias-left" />
            <span className="flex-1 bg-bias-center" />
            <span className="flex-1 bg-bias-right" />
          </span>
          GroundedNews
        </Link>
        <nav className="hidden items-center gap-1 text-sm lg:flex">
          {NAV.map((n) => {
            const active = isActive(n.href, pathname);
            return (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-md px-2.5 py-1.5 font-medium whitespace-nowrap text-muted-foreground transition-colors hover:text-foreground",
                  active && "bg-muted text-foreground"
                )}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          {pathname !== "/search" && <HeaderSearch />}
          <ThemeToggle />
          <NavMenu pathname={pathname} />
        </div>
      </div>
    </header>
  );
}
