"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS: { href: string; label: string }[] = [
  { href: "/", label: "Dashboard" },
  { href: "/breaches", label: "Breaches" },
  { href: "/settings", label: "Settings" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Nav() {
  const pathname = usePathname();
  return (
    <nav
      // safe-bottom (globals.css) clears the iOS home indicator via
      // env(safe-area-inset-bottom); kept in CSS, not an inline style
      // attribute, so the strict CSP does not block it.
      className="safe-bottom sticky bottom-0 z-10 border-t border-zinc-200 bg-white/95 backdrop-blur dark:border-zinc-800 dark:bg-black/95"
      aria-label="Primary"
    >
      <ul className="mx-auto flex max-w-5xl items-center justify-around px-2 py-1 text-sm font-medium">
        {LINKS.map((link) => {
          const active = isActive(pathname, link.href);
          return (
            <li key={link.href} className="flex-1">
              <Link
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={`tap w-full rounded-md text-center transition-colors ${
                  active
                    ? "text-blue-600 dark:text-blue-400"
                    : "text-zinc-600 hover:text-blue-600 dark:text-zinc-400 dark:hover:text-blue-400"
                }`}
              >
                {link.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
