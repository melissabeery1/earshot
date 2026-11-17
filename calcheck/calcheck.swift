// calcheck: lists your upcoming calendar events as JSON, for meeting prep.
// Reads the calendars the Mac's Calendar app already has (your Google account included), on this Mac only.
//
//   open -W -g "Meeting Prep.app" --args <out.json> [days]
//                       writes events from now to `days` ahead (default 14) to out.json, as one JSON array
//
// It's a tiny app (Meeting Prep.app, no Dock icon) rather than a plain command because macOS only lets an app
// that says why it wants calendars ask for them, and Hammerspoon doesn't. The prompt reads "Meeting Prep would
// like to access your calendars"; you allow it once.
//
// Rebuild: swiftc -O calcheck.swift -o "Meeting Prep.app/Contents/MacOS/calcheck" && codesign --force -s - "Meeting Prep.app"

import EventKit
import Foundation

let args = Array(CommandLine.arguments.dropFirst())
let outPath = args.first ?? "/dev/stdout"
let days = Double(args.count > 1 ? args[1] : "14") ?? 14
func write(_ text: String) { try? text.write(toFile: outPath, atomically: true, encoding: .utf8) }
let store = EKEventStore()
let done = DispatchSemaphore(value: 0)
var granted = false

if #available(macOS 14.0, *) {
    store.requestFullAccessToEvents { ok, _ in granted = ok; done.signal() }
} else {
    store.requestAccess(to: .event) { ok, _ in granted = ok; done.signal() }
}
done.wait()
guard granted else {
    write(#"{"error":"no calendar access"}"#)
    exit(2)
}

// "calendars" as the days argument lists the calendars this Mac can see instead (for setup checks).
if args.count > 1 && args[1] == "calendars" {
    let cals = store.calendars(for: .event).map { ["title": $0.title, "source": $0.source.title, "type": $0.source.sourceType.rawValue] as [String: Any] }
    write(String(data: try! JSONSerialization.data(withJSONObject: cals), encoding: .utf8)!)
    exit(0)
}

// A video link in the location, notes or URL marks an event as a call.
let linkPattern = try! NSRegularExpression(
    pattern: #"https?://[^\s<>"]*(zoom\.us|meet\.google\.com|teams\.microsoft\.com|teams\.live\.com|webex\.com|whereby\.com|facetime\.apple\.com|around\.co|riverside\.fm)[^\s<>"]*"#,
    options: [.caseInsensitive])

func link(_ text: String?) -> String? {
    guard let text, let m = linkPattern.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
          let r = Range(m.range, in: text) else { return nil }
    return String(text[r])
}

let now = Date()
let pred = store.predicateForEvents(withStart: now.addingTimeInterval(-3600), end: now.addingTimeInterval(days * 86400),
                                    calendars: nil)
let iso = ISO8601DateFormatter()
var out: [[String: Any]] = []
for ev in store.events(matching: pred) where !ev.isAllDay {
    let people = (ev.attendees ?? []).filter { !$0.isCurrentUser }.compactMap { $0.name ?? $0.url.absoluteString.replacingOccurrences(of: "mailto:", with: "") }
    let video = link(ev.location) ?? link(ev.notes) ?? link(ev.url?.absoluteString)
    out.append([
        "id": ev.calendarItemExternalIdentifier ?? ev.eventIdentifier ?? "",
        "title": ev.title ?? "(no title)",
        "start": iso.string(from: ev.startDate),
        "end": iso.string(from: ev.endDate),
        "start_ts": Int(ev.startDate.timeIntervalSince1970),   // exact moments, so nothing downstream converts zones
        "end_ts": Int(ev.endDate.timeIntervalSince1970),
        "calendar": ev.calendar.title,
        "people": people,
        "video": video ?? "",
        // your own events (a call titled with just a name, a "hold") have no guests and no link the Mac can see
        // (Google keeps Meet links where the Calendar app doesn't show them), so every timed event counts,
        // except daily repeats ("Take your Morning stack"), flights and anything over four hours.
        "invited": video != nil || !people.isEmpty,
        "is_call": !(ev.recurrenceRules ?? []).contains { $0.frequency == .daily }
                   && (ev.title ?? "").range(of: #"\b(flight|fly|flying)\b"#, options: [.regularExpression, .caseInsensitive]) == nil
                   && ev.endDate.timeIntervalSince(ev.startDate) <= 4 * 3600,
    ])
}
let data = try! JSONSerialization.data(withJSONObject: out, options: [.sortedKeys])
write(String(data: data, encoding: .utf8)!)
