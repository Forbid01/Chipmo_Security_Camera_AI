# Homebrew cask formula for the Sentry Agent macOS package.
#
# Usage:
#   brew tap sentry/agent <tap-url>
#   brew install --cask sentry-agent
#
# The download URL + checksum below are updated by the CI pipeline at
# release time — the placeholders let the file lint cleanly before the
# first release.

cask "sentry-agent" do
  version "0.1.0"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"

  url "https://downloads.sentry.mn/macos/sentry-agent-#{version}.pkg"
  name "Sentry Agent"
  desc "Edge agent that forwards RTSP camera streams to the Sentry cloud backend"
  homepage "https://sentry.mn"

  depends_on macos: ">= :monterey"
  depends_on cask: "docker"

  pkg "sentry-agent-#{version}.pkg"

  uninstall launchctl: "mn.sentry.agent",
            pkgutil:   "mn.sentry.agent",
            delete:    [
              "/usr/local/sentry-agent",
              "/Library/LaunchDaemons/mn.sentry.agent.plist",
            ]

  zap trash: [
    "/etc/sentry-agent",
    "/var/log/sentry-agent",
  ]
end
