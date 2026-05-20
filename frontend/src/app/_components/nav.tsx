import Link from "next/link";

const LINKS: { href: string; label: string }[] = [
  { href: "/", label: "Dashboard" },
  { href: "/breaches", label: "Breaches" },
  { href: "/settings", label: "Settings" },
];

export function Nav() {
  return (
    <nav className="sticky bottom-0 z-10 border-t border-zinc-200 bg-white/95 backdrop-blur dark:border-zinc-800 dark:bg-black/95">
      <ul className="mx-auto flex max-w-5xl items-center justify-around px-4 py-3 text-sm font-medium">
        {LINKS.map((link) => (
          <li key={link.href}>
            <Link
              href={link.href}
              className="text-zinc-600 transition-colors hover:text-blue-600 dark:text-zinc-400 dark:hover:text-blue-400"
            >
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
