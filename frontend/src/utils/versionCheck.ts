/**
 * OpenVox GUI - versionCheck.ts
 * 
 * Component documentation to be expanded.
 */
import { notifications } from '@mantine/notifications';

// Store the current version from build time
const BUILD_VERSION = import.meta.env.VITE_BUILD_VERSION || Date.now().toString();

// Check if error is due to module loading failure (usually after deployment)
export function isChunkLoadError(error: any): boolean {
  return (
    error?.message?.includes('Failed to fetch dynamically imported module') ||
    error?.message?.includes('Failed to import') ||
    error?.message?.includes('Loading chunk') ||
    error?.message?.includes('Loading CSS chunk') ||
    error?.name === 'ChunkLoadError'
  );
}

// Function to handle chunk load errors
export function handleChunkLoadError(): void {
  notifications.show({
    id: 'version-update',
    title: 'Application Updated',
    message: 'A new version is available. Please refresh the page to continue.',
    color: 'blue',
    autoClose: false,
    withCloseButton: false,
    onClose: () => window.location.reload(),
  });
}

// Version checker that periodically checks for updates
class VersionChecker {
  private checkInterval: number = 5 * 60 * 1000; // 5 minutes
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private currentVersion: string = BUILD_VERSION;
  
  start() {
    // Don't start if already running
    if (this.intervalId) return;
    
    // Check immediately on start
    this.checkVersion();
    
    // Then check periodically
    this.intervalId = setInterval(() => {
      this.checkVersion();
    }, this.checkInterval);
  }
  
  stop() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }
  
  private async checkVersion() {
    try {
      // Prefer JSON /api/version (stable across VIP backends) over
      // index.html ETag/Last-Modified which differs per console node.
      const response = await fetch('/api/version', {
        credentials: 'same-origin',
        cache: 'no-cache',
      });
      if (!response.ok) return;
      const data = await response.json();
      const versionIndicator = String(data?.version || '').trim();
      if (!versionIndicator) return;

      // Store the initial version indicator
      if (!window.sessionStorage.getItem('app-version')) {
        window.sessionStorage.setItem('app-version', versionIndicator);
        return;
      }

      // Check if version has changed
      const storedVersion = window.sessionStorage.getItem('app-version');
      if (storedVersion && storedVersion !== versionIndicator) {
        notifications.show({
          id: 'version-update-check',
          title: 'Update Available',
          message: 'A new version of the application is available. Refresh to get the latest features.',
          color: 'blue',
          autoClose: false,
          withCloseButton: true,
        });

        window.sessionStorage.setItem('app-version', versionIndicator);
        this.stop();
      }
    } catch (error) {
      // Silently fail - version checking is not critical
      console.debug('Version check failed:', error);
    }
  }
}

export const versionChecker = new VersionChecker();