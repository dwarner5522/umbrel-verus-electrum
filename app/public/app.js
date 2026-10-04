'use strict'

const $ = (id) => document.getElementById(id)
const number = new Intl.NumberFormat('en-US')

function setPill(state, label) {
	$('status-pill').dataset.state = state
	$('status-pill').textContent = label
}

function setProgress(fraction) {
	const percent = Math.max(0, Math.min(fraction * 100, 100))
	$('sync-fill').style.width = `${percent}%`
	$('sync-bar').setAttribute('aria-valuenow', percent.toFixed(1))
}

function render(status) {
	const ready = status.phase === 'ready'
	const known = status.dbHeight != null

	if (ready) {
		$('sync-percent').textContent = '100%'
		$('sync-label').textContent = 'Ready for wallets'
		setPill('synced', 'Ready')
	} else if (status.phase === 'syncing') {
		// Never show 100% until wallets can actually connect.
		$('sync-percent').textContent = `${Math.min(Math.floor(status.progress * 1000) / 10, 99.9)}%`
		$('sync-label').textContent = 'Indexing'
		setPill('syncing', 'Indexing')
	} else {
		$('sync-percent').textContent = '–'
		$('sync-label').textContent = status.phase === 'stopped' ? 'Stopped' : 'Starting'
		setPill(status.phase === 'stopped' ? 'error' : 'starting', status.phase === 'stopped' ? 'Stopped' : 'Starting')
	}
	setProgress(known ? status.progress : 0)

	$('sync-message').textContent =
		known && status.daemonHeight > 0
			? `Block ${number.format(status.dbHeight)} of ${number.format(status.daemonHeight)}${ready ? '' : ' · the first index takes several hours'}`
			: status.message || ''

	$('version').textContent = status.version ? `${status.version} · Verus mainnet` : 'ElectrumX'
	$('stat-db').textContent = known ? number.format(status.dbHeight) : '–'
	$('stat-node').textContent = known && status.daemonHeight > 0 ? number.format(status.daemonHeight) : '–'
	$('stat-sessions').textContent = known ? number.format(status.sessions) : '–'
	$('stat-uptime').textContent = status.uptime || '–'

	const {host, port, protocol} = status.connect
	$('host').textContent = host || location.hostname
	$('port').textContent = port
	$('protocol').textContent = protocol.toUpperCase()
	$('server').textContent = `${host || location.hostname}:${port}:${protocol}`
	$('connect-hint').textContent = ready
		? 'Add this as a custom Electrum server for VRSC in your wallet.'
		: 'Wallets can connect once the index has caught up with your Verus node.'

	$('error').hidden = !status.error
	$('error').textContent = status.error || ''
	if (status.error) setPill('error', 'Attention')
}

async function refresh() {
	try {
		const response = await fetch('api/status', {cache: 'no-store'})
		if (!response.ok) throw new Error(`HTTP ${response.status}`)
		render(await response.json())
	} catch {
		setPill('error', 'Offline')
		$('sync-message').textContent = 'Cannot reach the app. Retrying…'
	}
}

async function refreshLog() {
	if (!$('log-details').open) return
	try {
		const {lines} = await (await fetch('api/logs', {cache: 'no-store'})).json()
		const log = $('log')
		const pinned = log.scrollTop + log.clientHeight >= log.scrollHeight - 24
		log.textContent = lines.length ? lines.join('\n') : 'The log is empty.'
		if (pinned) log.scrollTop = log.scrollHeight
	} catch {
		// keep showing the last log we had
	}
}

async function copyText(text) {
	try {
		await navigator.clipboard.writeText(text)
		return true
	} catch {
		// The Clipboard API only exists in secure contexts, and Umbrel is usually opened over plain http.
		const field = document.createElement('textarea')
		field.value = text
		field.setAttribute('readonly', '')
		field.style.cssText = 'position:fixed;top:0;left:0;opacity:0'
		document.body.append(field)
		field.select()
		let copied = false
		try {
			copied = document.execCommand('copy')
		} catch {}
		field.remove()
		return copied
	}
}

for (const button of document.querySelectorAll('[data-copy]')) {
	button.addEventListener('click', async () => {
		button.textContent = (await copyText($(button.dataset.copy).textContent)) ? 'Copied' : 'Select to copy'
		setTimeout(() => (button.textContent = 'Copy'), 2000)
	})
}

$('log-details').addEventListener('toggle', refreshLog)

refresh()
setInterval(refresh, 3000)
setInterval(refreshLog, 5000)
