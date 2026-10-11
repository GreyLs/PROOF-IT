import React from 'react';
import brandLogo from '../public/brand/logo_01.svg?raw';

// Trusted, build-time brand artwork. Keep its exact paths; recolor only the mark.
const gradients = ['auth-brand-silver', 'auth-brand-lilac', 'auth-brand-violet'];
const markPaths = (brandLogo.match(/<path\b[^>]*\/>/g) || []).slice(0, 3)
  .map((path, index) => path.replace(/\s+id="[^"]*"/, '')
    .replace(/fill="#[^"]*"/, `fill="url(#${gradients[index]})"`)).join('');

/** Login-only decorative brand composition. No model calls or user data. */
export function AuthTechBackground() {
  return <div className="auth-brand-constellation" aria-hidden="true">
    <svg viewBox="0 0 520 380" fill="none" xmlns="http://www.w3.org/2000/svg" focusable="false">
      <defs>
        <linearGradient id="auth-brand-silver" x1="0" y1="0" x2="110" y2="115" gradientUnits="userSpaceOnUse"><stop stopColor="#fff5ff"/><stop offset="1" stopColor="#cda7ec"/></linearGradient>
        <linearGradient id="auth-brand-lilac" x1="30" y1="0" x2="100" y2="110" gradientUnits="userSpaceOnUse"><stop stopColor="#e8beff"/><stop offset="1" stopColor="#b66aff"/></linearGradient>
        <linearGradient id="auth-brand-violet" x1="45" y1="55" x2="115" y2="120" gradientUnits="userSpaceOnUse"><stop stopColor="#bb92ff"/><stop offset="1" stopColor="#7152e8"/></linearGradient>
        <linearGradient id="auth-orbit-line" x1="62" y1="30" x2="459" y2="340" gradientUnits="userSpaceOnUse"><stop stopColor="#eacbff" stopOpacity=".52"/><stop offset=".5" stopColor="#b789dc" stopOpacity=".32"/><stop offset="1" stopColor="#ddadff" stopOpacity=".65"/></linearGradient>
        <linearGradient id="auth-glass" x1="0" y1="0" x2="62" y2="62"><stop stopColor="#dfb5ff" stopOpacity=".16"/><stop offset="1" stopColor="#7133a4" stopOpacity=".25"/></linearGradient>
        <radialGradient id="auth-brand-wash"><stop stopColor="#ae58f2" stopOpacity=".23"/><stop offset="1" stopColor="#9a45db" stopOpacity="0"/></radialGradient>
      </defs>
      <ellipse cx="260" cy="182" rx="210" ry="158" fill="url(#auth-brand-wash)"/>
      <g stroke="url(#auth-orbit-line)" strokeWidth="1.1">
        <ellipse cx="260" cy="182" rx="198" ry="115" transform="rotate(-16 260 182)"/>
        <ellipse cx="260" cy="182" rx="198" ry="115" transform="rotate(44 260 182)"/>
        <ellipse cx="260" cy="182" rx="198" ry="115" transform="rotate(104 260 182)"/>
      </g>
      <g data-brand-mark="fsp" transform="translate(204 118) scale(.92)" dangerouslySetInnerHTML={{__html: markPaths}}/>
      <g fill="#d9baff" fontFamily="JetBrains,monospace" textAnchor="middle">
        <text x="260" y="258" fontSize="10" letterSpacing="3.4" opacity=".70">PROOFIT</text>
      </g>
      <g transform="translate(73 204) rotate(-12 30 30)">
        <rect width="60" height="60" rx="17" fill="url(#auth-glass)" stroke="#deb9ff" strokeOpacity=".42"/>
        <path d="M25 21L15 30L25 39M35 21L45 30L35 39M32 18L28 42" stroke="#efdbff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
      </g>
      <g transform="translate(385 78) rotate(12 30 30)">
        <rect width="60" height="60" rx="17" fill="url(#auth-glass)" stroke="#deb9ff" strokeOpacity=".42"/>
        <path d="M30 16L43 22V31C43 40 35 44 30 46C25 44 17 40 17 31V22L30 16Z" stroke="#efdbff" strokeWidth="1.8" strokeLinejoin="round"/>
        <path d="M24 30L28 34L36 26" stroke="#efdbff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
      </g>
      <g transform="translate(300 304) rotate(-9 26 26)">
        <rect width="52" height="52" rx="15" fill="url(#auth-glass)" stroke="#deb9ff" strokeOpacity=".42"/>
        <path d="M17 35L35 17M20 17H35V32" stroke="#efdbff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
      </g>
      <g fill="#e9ceff" opacity=".70"><circle cx="162" cy="77" r="2"/><circle cx="419" cy="244" r="2"/><circle cx="230" cy="323" r="2"/></g>
    </svg>
  </div>;
}
