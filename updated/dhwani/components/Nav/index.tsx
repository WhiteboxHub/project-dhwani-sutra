"use client";
import Link from 'next/link';
import { useState } from 'react';
import { Menu, X } from 'lucide-react';

export default function Navbar() {
  const [open, setOpen] = useState(false);

  return (
    <nav className="w-full bg-slate-900 text-white shadow-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <h1 className="text-xl font-bold">My App</h1>

        <div className="hidden md:flex items-center gap-6">
          <Link href="/pushtotalk" className="rounded-xl px-4 py-2 hover:bg-slate-800 transition">
            Sender
          </Link>
          <Link href="/listener" className="rounded-xl px-4 py-2 hover:bg-slate-800 transition">
            Listener
          </Link>
        </div>

        <button
          className="md:hidden rounded-xl p-2 hover:bg-slate-800"
          onClick={() => setOpen(!open)}
          aria-label="Toggle Menu"
        >
          {open ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {open && (
        <div className="md:hidden border-t border-slate-800 px-4 pb-4">
          <div className="flex flex-col gap-2 pt-4">
            <Link
              href="/pushtotalk"
              className="rounded-xl px-4 py-2 hover:bg-slate-800 transition"
              onClick={() => setOpen(false)}
            >
              Sender
            </Link>
            <Link
              href="/listener"
              className="rounded-xl px-4 py-2 hover:bg-slate-800 transition"
              onClick={() => setOpen(false)}
            >
              Listener
            </Link>
          </div>
        </div>
      )}
    </nav>
  );
}