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
  title: 'EvalForge - AI Release Assurance',
  description:
    'Decide whether an AI model or prompt change is safe to release using reproducible evaluation evidence.',
  openGraph: {
    title: 'EvalForge',
    description: 'Evidence before release.',
    images: [
      {
        url: '/og.png',
        width: 1536,
        height: 1024,
        alt: 'EvalForge AI release assurance workbench',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'EvalForge',
    description: 'Evidence before release.',
    images: ['/og.png'],
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
