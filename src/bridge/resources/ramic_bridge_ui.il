;RAMIC Bridge — CIW monitor (optional UI companion)
;RBM = RB Monitor
;
; Split out of ``ramic_bridge.il`` (2026-09-21).  This file owns the "RAMIC
; Bridge Monitor" form, the RAMIC banner menu and the pure-CIW cosmetic
; helpers.  Daemon lifecycle (RBStart/RBStop/RBStopAll), IPC framing, the
; per-request CDS.log capture and the auto-start stay in the core file.
;
; Load order matters: virtuoso_setup.il loads ramic_bridge.il first and this
; file second, because every widget below reads configuration globals
; (RBPort / RBLocal / RBEcho / RBDLog / RBDLogPath) created there and the
; callbacks call RBStart/RBStop/RBStopAll defined there.  The core file never
; depends on this one.
;
; The whole body sits inside a single boundp guard so that loading this file
; alone (without the core) prints one line and installs nothing -- instead of
; half-building a form/menu whose callbacks would only fail when clicked.
if(boundp('RBPort) then
progn(

; ============================================================================
; GUI Components for the RAMIC Bridge Monitor
; ============================================================================
; Re-running hiCreateAppForm with the same ?name *does* work on this IC build
; (it replaces the existing form), so layout edits applied via reload() take
; effect by setting RBMonInstalled = nil before reloading.  hiInsertBannerMenu
; isn't as friendly -- repeating it stacks the menu in the banner -- so the
; menu portion is gated separately further below.
;
; Guard checks the *value* (with a boundp check on the side, so a fresh
; SKILL session whose RBMonInstalled is unbound doesn't error on the value
; read).  ``RBMonInstalled = nil`` on its own is enough to force a rebuild
; on the next reload; nothing here needs SKILL's missing makunbound/unset.
unless(boundp('RBMonInstalled) && RBMonInstalled
progn(
; ----------------------------------------------------------------------
; Status section -- four stacked labels.  Section header sits on its
; own row; the four data labels are populated by RBMRefresh().  Old
; single-RBMState label is kept for back-compat (other code may set it
; out of habit) but no longer shown in the layout.
; ----------------------------------------------------------------------
; Legacy single-line label kept for back-compat with code that still
; sets RBMonitor->RBMState->value.  Not laid out in the new form.
; Empty labelText would error out on hiCreateLabel ("required parameter"),
; so seed with one space.
RBMState = hiCreateLabel(?name 'RBMState ?labelText " " ?justification CDS_JUSTIFY_LEFT)

RBMSecStatus = hiCreateLabel(
    ?name 'RBMSecStatus
    ?labelText "STATUS"
    ?justification CDS_JUSTIFY_LEFT)

RBMStatusIcon = hiCreateLabel(
    ?name 'RBMStatusIcon
    ?labelText "(unknown)"
    ?justification CDS_JUSTIFY_LEFT)

RBMHostLabel = hiCreateLabel(
    ?name 'RBMHostLabel
    ?labelText " "
    ?justification CDS_JUSTIFY_LEFT)

RBMConnLabel = hiCreateLabel(
    ?name 'RBMConnLabel
    ?labelText " "
    ?justification CDS_JUSTIFY_LEFT)

RBMStatsLabel = hiCreateLabel(
    ?name 'RBMStatsLabel
    ?labelText " "
    ?justification CDS_JUSTIFY_LEFT)

; ----------------------------------------------------------------------
; Control section
; ----------------------------------------------------------------------
RBMSecControl = hiCreateLabel(
    ?name 'RBMSecControl
    ?labelText "CONTROL"
    ?justification CDS_JUSTIFY_LEFT)

RBMBtnRefresh = hiCreateButton(
    ?name 'RBMBtnRefresh
    ?buttonText "Refresh"
    ?callback "RBMRefresh()")

RBMBtnStart = hiCreateButton(
    ?name 'RBMBtnStart
    ?buttonText "Start"
    ?callback "RBStart() RBMRefresh()")

RBMBtnStop = hiCreateButton(
    ?name 'RBMBtnStop
    ?buttonText "Stop"
    ?callback "RBStop() RBMRefresh()")

RBMIntPort = hiCreateIntField(
    ?name 'RBMIntPort
    ?prompt "Port"
    ?value RBPort
    ?defValue RBPort
    ?callback nil)

RBMBolLocal = hiCreateBooleanButton(
    ?name 'RBMBolLocal
    ?buttonText "Local connect only (127.0.0.1)"
    ?value RBLocal
    ?defValue RBLocal
    ?callback nil)

; ----------------------------------------------------------------------
; Options section -- three boolean toggles, one per row.
; ----------------------------------------------------------------------
RBMSecOptions = hiCreateLabel(
    ?name 'RBMSecOptions
    ?labelText "OPTIONS"
    ?justification CDS_JUSTIFY_LEFT)

RBMBolEcho = hiCreateBooleanButton(
    ?name 'RBMBolEcho
    ?buttonText "Echo bridging string"
    ?value RBEcho
    ?defValue RBEcho
    ?callback nil)

RBMBolLog = hiCreateBooleanButton(
    ?name 'RBMBolLog
    ?buttonText strcat("Daemon log (" RBDLogPath ")")
    ?value RBDLog
    ?defValue RBDLog
    ?callback nil)

; ----------------------------------------------------------------------
; Apply -- commits the form's checkbox / port edits back to SKILL
; globals (RBLocal / RBPort / RBDLog / RBEcho).  When Local / Port /
; Daemon-log changed, RBMApply() also restarts the daemon so the new
; bind setting takes effect.  Lives inline in the form (rather than as
; the Motif bottom 'Apply button) because this IC's hiCreateAppForm
; only accepts a fixed enum for ?buttonLayout, and 'Apply isn't in it.
; ----------------------------------------------------------------------
RBMBtnApply = hiCreateButton(
    ?name 'RBMBtnApply
    ?buttonText "Apply changes  (restarts daemon when port / mode / log toggles)"
    ?callback "RBMApply() RBMRefresh()")

; ----------------------------------------------------------------------
; Emergency action -- UID-scoped (only kills *this user's* daemons).
; ----------------------------------------------------------------------
RBMBtnStopAll = hiCreateButton(
    ?name 'RBMBtnStopAll
    ?buttonText "Kill MY daemons  (force, UID-scoped)"
    ?callback "RBStopAll() RBMRefresh()")

; Form geometry: each section is roughly y = [section_y .. section_y+section_h].
;   Status :  y=10..150   (header + 4 data lines)
;   Control:  y=155..255  (header + buttons row + port row)
;   Options:  y=265..380  (header + 3 checkboxes + Apply button)
;   Action :  y=435..475  (Kill button)
; Width 720 fits "<ip> (<host>) ipc=... pid=... bind=...:..." comfortably.
;
; Note: form geometry is captured at first hiCreateAppForm call.  Reloading
; this file updates procedure bodies but not the live form -- close
; the form and toggle RBMonInstalled=nil before reload to pick up layout
; changes (or restart Virtuoso).  Apply lives as an inline button rather
; than ?buttonLayout 'Apply because that symbol isn't in this IC build's
; valid enum (only 'Empty/'OK/'Close/'OKCancel/'OKCancelApply/...).
hiCreateAppForm(
    ?name 'RBMonitor
    ?formTitle "RAMIC Bridge Monitor"
    ?fields list(
        ; --- STATUS ---
        list(RBMSecStatus    20:10  680:20)
        list(RBMStatusIcon   30:35  680:24)
        list(RBMHostLabel    30:60  680:20)
        list(RBMConnLabel    30:85  680:20)
        list(RBMStatsLabel   30:110 680:20)

        ; --- CONTROL ---
        list(RBMSecControl   20:155 680:20)
        list(RBMBtnRefresh   30:180 110:28)
        list(RBMBtnStart    150:180 110:28)
        list(RBMBtnStop     270:180 110:28)
        list(RBMIntPort      30:220 200:28 50)

        ; --- OPTIONS (three checkboxes + inline Apply, left-aligned) ---
        list(RBMSecOptions   20:265 680:20)
        list(RBMBolLocal     30:290 660:28)
        list(RBMBolEcho      30:320 660:28)
        list(RBMBolLog       30:350 660:28)
        list(RBMBtnApply     30:385 660:32)

        ; --- ACTION ---
        list(RBMBtnStopAll   30:435 660:32)
    )
    ; ``Empty`` drops the default OK/Cancel/Help row (~50 px).  Apply
    ; appears as the inline RBMBtnApply button above; pressing it
    ; calls RBMApply() which diffs form values vs live RBLocal/RBPort/
    ; RBDLog and restarts the daemon if any toggled.  ``?callback``
    ; is also wired to RBMApply so future layout changes that re-add
    ; an OK button keep the same semantics.
    ?buttonLayout 'Empty
    ?help ""
    ?initialSize  720:520
    ?minSize      720:520
    ?maxSize      720:520
    ?mapCB        "RBMRefresh()"
    ?callback     "RBMApply()"
)

; ============================================================================
; Menu Integration
; ============================================================================

RBMonInstalled = t
)
) ; end unless(boundp 'RBMonInstalled) + progn

; ---------------------------------------------------------------------
; Banner menu -- guarded SEPARATELY from the form because hiInsertBanner
; Menu has no remove-and-replace primitive on this IC build.  We need
; the form to be re-creatable (toggle RBMonInstalled = nil + reload),
; but the menu must stay built once per Virtuoso session.
; ---------------------------------------------------------------------
unless(boundp('RBMenuInstalled) && RBMenuInstalled
    ramicMenu = hiCreatePulldownMenu(
        'ramicMenu
        "RAMIC"
        list(
            hiCreateMenuItem(
                ?name 'RAMIC_Bridge
                ?itemText "RAMIC Bridge..."
                ?callback "hiDisplayForm(RBMonitor)"
            )
            hiCreateMenuItem(
                ?name 'RAMIC_PrintLines10
                ?itemText "Print 10 Empty Lines"
                ?callback "RBPrintEmptyLines(10)"
            )
            hiCreateMenuItem(
                ?name 'RAMIC_PrintLines20
                ?itemText "Print 20 Empty Lines"
                ?callback "RBPrintEmptyLines(20)"
            )
        )
    )
    hiInsertBannerMenu(window(1) ramicMenu 3)
    RBMenuInstalled = t
)

procedure(RBMRefresh()
    ; Re-read SKILL state and repaint the monitor form.
    ; - State label gets ipc handle + os pid + bind:port so debugging
    ;   doesn't require a separate `ss -tlnp` round-trip.
    ; - Other widgets just mirror the current SKILL globals.
    when(boundp('RBMonInstalled)
        let((alive bind hostStr statusText newForm)
            alive = (boundp('RBIpc) && ipcIsAliveProcess(RBIpc))
            ; Bind: prefer captured (RBLastBind), fall back to derived
            bind = if(RBLastBind && strlen(RBLastBind) > 0
                RBLastBind
                sprintf(nil "%s:%d"
                    if(RBLocal "127.0.0.1" "0.0.0.0")
                    RBPort))
            ; Identity: "IP (hostname)" if both, else whichever
            hostStr = cond(
                ((strlen(RBLastIP) > 0 && strlen(RBLastHost) > 0)
                    sprintf(nil "%s (%s)" RBLastIP RBLastHost))
                ((strlen(RBLastIP) > 0)   RBLastIP)
                ((strlen(RBLastHost) > 0) RBLastHost)
                (t ""))
            ; Status indicator -- text only.  ?foreground colour writes
            ; on Motif labels are silently ignored on this IC build,
            ; so we use unicode glyphs for the visual cue instead.
            statusText = cond(
                (alive && RBLastPid              "[OK]      Running")
                (alive                           "[...]     Starting / Suspect")
                (t                               "[--]      Down"))

            ; --- New-style form (post-restart): RBMStatusIcon exists. ---
            ; --- Old-style form (legacy): only RBMState exists.       ---
            newForm = car(errset(RBMonitor->RBMStatusIcon))
            if(newForm
                progn(
                    errset(RBMonitor->RBMStatusIcon->value = statusText)
                    errset(RBMonitor->RBMHostLabel->value =
                        if(strlen(hostStr) > 0
                            sprintf(nil "Host:  %s" hostStr)
                            "Host:  (banner not yet received)"))
                    errset(RBMonitor->RBMConnLabel->value =
                        if(alive
                            sprintf(nil "ipc=%L     pid=%L     bind=%s"
                                RBIpc RBLastPid bind)
                            if(RBLastPid
                                sprintf(nil "(last)  pid=%L  port=%d"
                                    RBLastPid RBPort)
                                " ")))
                    errset(RBMonitor->RBMStatsLabel->value =
                        if(alive
                            sprintf(nil "%d calls   %d errors   up %s"
                                RBStatCount RBStatErrors
                                RBFormatUptime(RBStatUptime))
                            " "))
                )
                ; Old form path -- pack everything into a single line
                errset(RBMonitor->RBMState->value =
                    if(alive
                        sprintf(nil
                            "RAMIC Bridge: Running   %s   ipc=%L  pid=%L  bind=%s   |   %d calls (%d err)  up %s"
                            hostStr RBIpc RBLastPid bind
                            RBStatCount RBStatErrors
                            RBFormatUptime(RBStatUptime))
                        if(RBLastPid
                            sprintf(nil "RAMIC Bridge: Down   (last %s pid=%L port=%d)"
                                if(strlen(hostStr) > 0 hostStr "host=?")
                                RBLastPid RBPort)
                            "RAMIC Bridge: Down")))
            )

            errset(RBMonitor->RBMIntPort->value = RBPort)
            errset(RBMonitor->RBMBolLocal->value = RBLocal)
            errset(RBMonitor->RBMBolEcho->value = RBEcho)
            errset(RBMonitor->RBMBolLog->value = RBDLog)
        )
    )
)

procedure(RBMApply()
    ; Apply changes from the monitor form to the configuration
	when(boundp('RBMonInstalled)
	RBEcho = RBMonitor->RBMBolEcho->value
	prog((refresh)
	unless(RBMonitor->RBMBolLocal->value == RBLocal
		RBLocal = RBMonitor->RBMBolLocal->value
		refresh = t
	)
	unless(RBMonitor->RBMIntPort->value == RBPort
		RBPort = RBMonitor->RBMIntPort->value
		refresh = t
	)
	unless(RBMonitor->RBMBolLog->value == RBDLog
		RBDLog = RBMonitor->RBMBolLog->value
		refresh = t
	)
	when(refresh
		RBStop()
		RBStart()
	)
	)
	)
)

procedure(RBFormatUptime(s)
    ; Render a seconds-int as compact "<H>h <M>m" / "<M>m <S>s" / "<S>s".
    ; Avoids quotient / mod / fix; only ``truncate`` (towards zero) +
    ; subtraction, which are stable across all observed IC builds.
    let((sec h m)
        sec = s
        h = truncate(sec / 3600.0)
        sec = sec - h * 3600
        m = truncate(sec / 60.0)
        sec = sec - m * 60
        cond(
            ((h > 0) sprintf(nil "%dh %dm" h m))
            ((m > 0) sprintf(nil "%dm %ds" m sec))
            (t sprintf(nil "%ds" sec))))
)

procedure(RBPrintEmptyLines(@optional (n 10))
    ; Push old CIW lines off-screen for a clean visual workspace.
    ; Default 10; pass any positive integer.
    for(i 1 n printf("\n"))
)
)
else
printf("[RAMIC Bridge UI] not installed: load ramic_bridge.il first (RBPort unbound).\n")
)
