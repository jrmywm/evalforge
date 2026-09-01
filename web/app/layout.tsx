import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const geistSans = Geist({ variable: '--font-geist-sans', subsets: ['latin'] });
const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  metadataBase: new URL('http://localhost:5173'),
  title: 'EvalForge · Evaluation Control Room',
  description:
    'Inspect local LLM regression runs, release gates, and failure evidence.',
  openGraph: {
    title: 'EvalForge',
    description: 'LLM evaluation control room',
    images: [
      {
        url: '/og.png',
        width: 1536,
        height: 1024,
        alt: 'EvalForge LLM evaluation control room',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'EvalForge',
    description: 'LLM evaluation control room',
    images: ['/og.png'],
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
