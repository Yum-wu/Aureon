/**
 * appVersion.ts — centralized app version source
 */

declare const __APP_VERSION__: string;

function readPackageVersion(): string {
  try {
    return typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : '0.0.0-dev';
  } catch {
    return '0.0.0-dev';
  }
}

let cachedVersion: string | null = null;

export function getAppVersion(): string {
  if (!cachedVersion) cachedVersion = readPackageVersion();
  return cachedVersion;
}

export function getCacheBuster(): string {
  return `aureon@${getAppVersion()}`;
}
