package app.saavdhan.ui

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ComponentName
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.saavdhan.core.Level
import app.saavdhan.notify.MessageListenerService
import java.util.Locale

class MainActivity : ComponentActivity() {
    private val vm: AppViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handleIntent(intent)
        setContent { SaavdhanTheme { App(vm) } }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(i: Intent?) {
        val shared = when (i?.action) {
            Intent.ACTION_SEND -> i.getStringExtra(Intent.EXTRA_TEXT)
            Intent.ACTION_PROCESS_TEXT -> i.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT)?.toString()
            else -> i?.getStringExtra(EXTRA_TEXT)
        }
        if (!shared.isNullOrBlank()) vm.load(shared, i?.getStringExtra(EXTRA_SENDER))
    }

    companion object {
        const val EXTRA_TEXT = "app.saavdhan.TEXT"
        const val EXTRA_SENDER = "app.saavdhan.SENDER"
    }
}

private val Saffron = Color(0xFFE8710A)
private val Danger = Color(0xFFC62828)
private val Warn = Color(0xFFEF8F00)
private val Safe = Color(0xFF2E7D32)

@Composable
fun SaavdhanTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = lightColorScheme(primary = Saffron, secondary = Color(0xFF1B5E20)), content = content)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun App(vm: AppViewModel) {
    var tab by remember { mutableIntStateOf(0) }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Saavdhan · सावधान", fontWeight = FontWeight.Bold) },
                actions = {
                    TextButton(onClick = { vm.updateLang(if (vm.lang == "en") "hi" else "en") }) {
                        Text(if (vm.lang == "en") "हिंदी" else "English")
                    }
                },
            )
        },
        bottomBar = {
            NavigationBar {
                listOf(Triple("Check", Icons.Default.Shield, 0), Triple("Benchmark", Icons.Default.Speed, 1),
                    Triple("Setup", Icons.Default.Settings, 2)).forEach { (label, icon, i) ->
                    NavigationBarItem(selected = tab == i, onClick = { tab = i }, icon = { Icon(icon, null) }, label = { Text(label) })
                }
            }
        },
    ) { pad ->
        Box(Modifier.padding(pad).fillMaxSize()) {
            when (tab) {
                0 -> CheckScreen(vm)
                1 -> BenchmarkScreen(vm)
                else -> SetupScreen(vm)
            }
        }
    }
}

@Composable
fun CheckScreen(vm: AppViewModel) {
    Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        OfflineBadge()
        OutlinedTextField(
            value = vm.text, onValueChange = { vm.text = it }, modifier = Modifier.fillMaxWidth().heightIn(min = 120.dp),
            label = { Text(if (vm.lang == "hi") "संदेश यहाँ पेस्ट करें" else "Paste or share a message here") },
        )
        OutlinedTextField(
            value = vm.sender, onValueChange = { vm.sender = it }, singleLine = true, modifier = Modifier.fillMaxWidth(),
            label = { Text(if (vm.lang == "hi") "भेजने वाला (वैकल्पिक)" else "Sender (optional), e.g. AX-HDFCBK-S or 98xxxxxxxx") },
        )
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Samples.all.forEach { s -> AssistChip(onClick = { vm.load(s.text, s.sender) }, label = { Text(s.label) }) }
        }
        Button(onClick = { vm.check() }, enabled = vm.ready && vm.text.isNotBlank(), modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Default.Search, null); Spacer(Modifier.width(8.dp))
            Text(if (vm.lang == "hi") "जांचें" else "Check message")
        }
        vm.result?.let { r -> ResultCard(vm, r) }
    }
}

@Composable
fun OfflineBadge() {
    Row(
        Modifier.fillMaxWidth().background(Color(0xFFE8F5E9), RoundedCornerShape(8.dp)).padding(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Default.AirplanemodeActive, null, tint = Safe)
        Spacer(Modifier.width(8.dp))
        Text("Runs 100% on this phone. No internet permission.", fontSize = 13.sp, color = Safe)
    }
}

@Composable
fun ResultCard(vm: AppViewModel, r: app.saavdhan.detect.Detector.Result) {
    val v = r.verdict
    val color = when (v.level) { Level.HIGH -> Danger; Level.MEDIUM -> Warn; Level.LOW -> Safe }
    Card(colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.08f)), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(if (v.level == Level.LOW) Icons.Default.CheckCircle else Icons.Default.Warning, null, tint = color)
                Spacer(Modifier.width(8.dp))
                Text(vm.detector.explainer.levelWords(v.level, vm.lang), color = color, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                Spacer(Modifier.weight(1f))
                Text("${(v.risk * 100).toInt()}%", color = color, fontWeight = FontWeight.Bold)
            }
            LinearProgressIndicator(progress = { v.risk.toFloat() }, color = color, modifier = Modifier.fillMaxWidth())
            Text(vm.template.lineSequence().drop(1).joinToString("\n"), fontSize = 14.sp)
            Text(
                String.format(Locale.US, "Detector %.2f ms (classifier %.2f ms%s) · %d signals",
                    r.totalMs, r.classifierMs, r.classifierLogit?.let { String.format(Locale.US, ", p=%.2f", 1 / (1 + Math.exp(-it))) } ?: ", rules only",
                    v.signals.size),
                fontSize = 11.sp, color = Color.Gray,
            )
            HorizontalDivider()
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.AutoAwesome, null, tint = Saffron)
                Spacer(Modifier.width(6.dp))
                Text(if (vm.lang == "hi") "Llama की सलाह (ऑन-डिवाइस)" else "Llama explanation (on-device)", fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.weight(1f))
                if (vm.llmRunning) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                else TextButton(onClick = { vm.explain() }) { Text(if (vm.llmText.isEmpty()) "Explain" else "Regenerate") }
            }
            vm.llmNote?.let { Text(it, fontSize = 12.sp, color = Color.Gray) }
            if (vm.llmText.isNotEmpty()) Text(vm.llmText, fontSize = 15.sp)
            vm.llmStats?.let { s ->
                Text(String.format(Locale.US, "TTFT %d ms · prefill %.1f tok/s · decode %.1f tok/s · peak RAM %d MB",
                    s.ttftMs, s.prefillTokPerSec, s.decodeTokPerSec, s.peakRssMb), fontSize = 11.sp, color = Color.Gray)
            }
        }
    }
}

@Composable
fun BenchmarkScreen(vm: AppViewModel) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("On-device benchmark", fontWeight = FontWeight.Bold, fontSize = 18.sp)
        Text("Measures detector latency (features, ExecuTorch classifier, rules) and Llama load time, " +
            "time-to-first-token, prefill/decode speed and peak memory. Turn on airplane mode first.", fontSize = 13.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { vm.runBenchmark(false) }, enabled = !vm.benchRunning) { Text("Detector only") }
            Button(onClick = { vm.runBenchmark(true) }, enabled = !vm.benchRunning) { Text("Detector + Llama") }
        }
        if (vm.benchText.isNotEmpty()) {
            OutlinedButton(onClick = {
                ctx.getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("benchmark", vm.benchText))
            }) { Icon(Icons.Default.ContentCopy, null); Spacer(Modifier.width(6.dp)); Text("Copy JSON for report") }
            SelectionContainer {
                Text(vm.benchText, fontFamily = FontFamily.Monospace, fontSize = 11.sp)
            }
        }
    }
}

@Composable
fun SetupScreen(vm: AppViewModel) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    var refresh by remember { mutableIntStateOf(0) }
    val notifPerm = rememberLauncherForNotif()
    val listenerOn = remember(refresh) {
        val flat = Settings.Secure.getString(ctx.contentResolver, "enabled_notification_listeners").orEmpty()
        flat.contains(ComponentName(ctx, MessageListenerService::class.java).flattenToString())
    }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        key(refresh) {
            StatusRow("Detector rules", true, "shared/rules.json loaded")
            StatusRow("ExecuTorch classifier", vm.detector.hasClassifier,
                if (vm.detector.hasClassifier) "scam_classifier.pte loaded in ${vm.detector.classifierLoadMs} ms" else "error: ${vm.detector.classifierError}")
            val mf = vm.llama.modelFile(); val tf = vm.llama.tokenizerFile()
            StatusRow("Llama model (ExecuTorch)", mf != null && tf != null,
                if (mf != null && tf != null) "${mf.name} (${mf.length() / 1_000_000} MB) + ${tf.name}" else "Not found. Push the files with adb:")
            if (mf == null || tf == null) {
                SelectionContainer {
                    Text("adb push Llama-3.2-1B-Instruct-SpinQuant_INT4_EO8.pte tokenizer.model ${vm.llama.modelDir.absolutePath}/",
                        fontFamily = FontFamily.Monospace, fontSize = 11.sp)
                }
            }
            StatusRow("Message alerts", listenerOn, if (listenerOn) "Watching SMS and WhatsApp notifications" else "Allow notification access to get automatic warnings")
        }
        Button(onClick = { ctx.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) }) { Text("Open notification access settings") }
        if (Build.VERSION.SDK_INT >= 33) OutlinedButton(onClick = { notifPerm() }) { Text("Allow alert notifications") }
        OutlinedButton(onClick = { refresh++ }) { Text("Refresh status") }
        Text("Privacy: messages are analysed in memory and never stored or sent. The app does not request the INTERNET permission.",
            fontSize = 12.sp, color = Color.Gray)
    }
}

@Composable
private fun rememberLauncherForNotif(): () -> Unit {
    val launcher = androidx.activity.compose.rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    return { if (Build.VERSION.SDK_INT >= 33) launcher.launch(Manifest.permission.POST_NOTIFICATIONS) }
}

@Composable
fun StatusRow(title: String, ok: Boolean, detail: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(if (ok) Icons.Default.CheckCircle else Icons.Default.ErrorOutline, null, tint = if (ok) Safe else Warn)
        Spacer(Modifier.width(10.dp))
        Column {
            Text(title, fontWeight = FontWeight.SemiBold)
            Text(detail, fontSize = 12.sp, color = Color.Gray)
        }
    }
}
