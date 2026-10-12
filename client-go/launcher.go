package main

import (
	"bytes"
	_ "embed"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

//go:embed launcher/FolioCast.sh
var embeddedLauncher []byte

const (
	DefaultLauncherPath = "/mnt/us/documents/FolioCast.sh"
	LauncherMarkerLine  = "# Name: FolioCast"
)

func isLauncherMarkerPresent(data []byte) bool {
	s := string(data)
	return strings.Contains(s, LauncherMarkerLine) || strings.Contains(s, "# Name: Transit Tracker")
}

// resolveLauncherPath scans args for -launcher or -launcher=, defaulting to DefaultLauncherPath.
func resolveLauncherPath(args []string) string {
	for i, arg := range args {
		if (arg == "-launcher" || arg == "--launcher") && i+1 < len(args) {
			val := strings.TrimSpace(args[i+1])
			if val != "" {
				return val
			}
		}
		if strings.HasPrefix(arg, "-launcher=") || strings.HasPrefix(arg, "--launcher=") {
			parts := strings.SplitN(arg, "=", 2)
			val := strings.TrimSpace(parts[1])
			if val != "" {
				return val
			}
		}
	}
	return DefaultLauncherPath
}

// selfUpdateLauncher compares the embedded launcher with the file at launcherPath.
// Per spec §8: It rewrites the file atomically only when BOTH:
// 1. The existing file contains the marker line "# Name: Transit Tracker"
// 2. Its bytes differ from the embedded copy.
func selfUpdateLauncher(launcherPath string) error {
	if len(embeddedLauncher) == 0 {
		return nil
	}
	data, err := osReadFile(launcherPath)
	if err != nil {
		// File does not exist or cannot be read; do not create
		return nil
	}
	if !isLauncherMarkerPresent(data) {
		return nil
	}
	if bytes.Equal(data, embeddedLauncher) {
		return nil
	}

	dir := filepath.Dir(launcherPath)
	tmpPath := filepath.Join(dir, fmt.Sprintf(".launcher_update_%d.tmp", os.Getpid()))
	if err := osWriteFile(tmpPath, embeddedLauncher, 0755); err != nil {
		return err
	}
	if err := osRename(tmpPath, launcherPath); err != nil {
		_ = osRemove(tmpPath)
		return err
	}
	return nil
}
