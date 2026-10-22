package com.renaldibosco.echolang;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.InputType;
import android.text.Spannable;
import android.text.TextWatcher;
import android.text.style.ForegroundColorSpan;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MainActivity extends Activity {
    // colours
    static final int BG = 0xFF0F1419, PANEL = 0xFF151B23, BAR = 0xFF1C2430, TEXT = 0xFFE6EDF3, DIM = 0xFF8B949E;
    static final int ACCENT = 0xFF3FB950, KEYWORD = 0xFFFF7B72, STRING = 0xFFA5D6FF, COMMENT = 0xFF8B949E,
            NUMBER = 0xFF79C0FF, BIO = 0xFF7EE787, ERROR = 0xFFFF7B72;

    static final Pattern P_COMMENT = Pattern.compile("#[^\\n]*");
    static final Pattern P_STRING = Pattern.compile("\"\"\"[\\s\\S]*?\"\"\"|\"[^\"\\n]*\"|'[^'\\n]*'");
    static final Pattern P_NUMBER = Pattern.compile("\\b\\d+(\\.\\d+)?\\b");
    static final Pattern P_KEYWORD = Pattern.compile("\\b(set|to|say|ask|into|if|then|else|end|repeat|times|while|for|each|in|from|step|"
            + "break|continue|stop|skip|define|return|try|catch|fail|use|record|fn|add|and|or|not|xor|nand|nor|xnor|is|"
            + "true|false|yes|no|nothing|global|pass|forever|ai)\\b");
    static final Pattern P_BIO = Pattern.compile("\\b(dna|gc|at|gc_count|base_counts|complement|reverse_complement|revcomp|transcribe|"
            + "translate|find_orfs|find_motif|tm|primer_check|primer_info|design_primers|pcr_program|restriction_sites|digest|"
            + "align|protein_mass|isoelectric_point|gravy|protein_info|parse_fasta|read_fasta|to_fasta|gel|dilute|copy_number|"
            + "mutate|hamming|codon_usage|enzymes|truth_table|half_adder|full_adder|gate|train|predict|linear_fit|cluster)\\b");

    EditText editor;
    TextView output, status;
    ScrollView outputScroll;
    Button runBtn;
    Handler ui = new Handler(Looper.getMainLooper());
    SharedPreferences prefs;
    String currentName = "main";
    volatile boolean running = false, stopRequested = false;
    final StringBuilder pending = new StringBuilder();
    boolean flushScheduled = false;
    PyObject app;
    final Runnable highlighter = this::highlight;
    boolean highlighting = false;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        prefs = getSharedPreferences("echo", MODE_PRIVATE);
        if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
        app = Python.getInstance().getModule("echo_app");
        buildUi();
        String saved = prefs.getString("code", null);
        currentName = prefs.getString("name", "main");
        if (saved == null) { saved = app.callAttr("example", "hello").toString(); currentName = "hello"; }
        editor.setText(saved);
        updateStatus("Ready. Tap ▶ Run.");
    }

    @Override
    protected void onPause() {
        super.onPause();
        prefs.edit().putString("code", editor.getText().toString()).putString("name", currentName).apply();
    }

    // ------------------------------------------------------------------ layout
    int dp(float v) { return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics()); }

    Button button(String text, View.OnClickListener l, int color) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextColor(TEXT);
        b.setTextSize(14);
        b.setMinWidth(0);
        b.setMinimumWidth(0);
        b.setMinHeight(0);
        b.setMinimumHeight(0);
        b.setPadding(dp(12), dp(8), dp(12), dp(8));
        GradientDrawable g = new GradientDrawable();
        g.setColor(color);
        g.setCornerRadius(dp(8));
        b.setBackground(g);
        b.setOnClickListener(l);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(dp(3), dp(4), dp(3), dp(4));
        b.setLayoutParams(lp);
        return b;
    }

    HorizontalScrollView row(View... views) {
        LinearLayout r = new LinearLayout(this);
        r.setOrientation(LinearLayout.HORIZONTAL);
        r.setGravity(Gravity.CENTER_VERTICAL);
        for (View v : views) r.addView(v);
        HorizontalScrollView h = new HorizontalScrollView(this);
        h.setHorizontalScrollBarEnabled(false);
        h.addView(r);
        h.setBackgroundColor(BAR);
        h.setPadding(dp(4), 0, dp(4), 0);
        return h;
    }

    void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(BG);

        TextView title = new TextView(this);
        title.setText("Echo  ·  bio language");
        title.setTextColor(TEXT);
        title.setTextSize(18);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setPadding(dp(14), dp(10), dp(14), dp(2));
        root.addView(title);

        status = new TextView(this);
        status.setTextColor(DIM);
        status.setTextSize(12);
        status.setPadding(dp(14), 0, dp(14), dp(6));
        root.addView(status);

        runBtn = button("▶ Run", v -> runOrStop(), 0xFF238636);
        root.addView(row(runBtn,
                button("Examples", v -> showExamples(), BAR + 0x00101010),
                button("Files", v -> showFiles(), PANEL),
                button("Save", v -> saveAs(), PANEL),
                button("New", v -> newFile(), PANEL),
                button("→ Java", v -> convert(true), PANEL),
                button("→ Python", v -> convert(false), PANEL),
                button("Check", v -> checkCode(), PANEL),
                button("AI key", v -> aiSettings(), PANEL),
                button("Guide", v -> showGuide(), PANEL),
                button("Share", v -> shareCode(), PANEL)));

        editor = new EditText(this);
        editor.setTypeface(Typeface.MONOSPACE);
        editor.setTextSize(14);
        editor.setTextColor(TEXT);
        editor.setBackgroundColor(PANEL);
        editor.setGravity(Gravity.TOP | Gravity.START);
        editor.setPadding(dp(12), dp(10), dp(12), dp(10));
        editor.setHorizontallyScrolling(false);
        editor.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE
                | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS | InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD);
        editor.setImeOptions(0x10000000 /* IME_FLAG_NO_PERSONALIZED_LEARNING */);
        editor.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int a, int b, int c) {}
            public void onTextChanged(CharSequence s, int a, int b, int c) {}
            public void afterTextChanged(Editable s) {
                if (highlighting) return;
                ui.removeCallbacks(highlighter);
                ui.postDelayed(highlighter, 350);
            }
        });
        root.addView(editor, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1.15f));

        // quick symbols for the phone keyboard
        List<View> keys = new ArrayList<>();
        for (final String k : Arrays.asList("⇥", "end", "(", ")", "\"", "[", "]", "{", "}", ":", "=", ",", ".", "#", "->", "say ", "set ")) {
            keys.add(button(k, v -> insert(k.equals("⇥") ? "    " : k), BG));
        }
        root.addView(row(keys.toArray(new View[0])));

        output = new TextView(this);
        output.setTypeface(Typeface.MONOSPACE);
        output.setTextSize(13);
        output.setTextColor(TEXT);
        output.setTextIsSelectable(true);
        output.setPadding(dp(12), dp(10), dp(12), dp(10));
        outputScroll = new ScrollView(this);
        outputScroll.setBackgroundColor(0xFF0A0D12);
        outputScroll.addView(output);
        root.addView(outputScroll, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 0.85f));

        setContentView(root);
    }

    void insert(String s) {
        int a = Math.max(editor.getSelectionStart(), 0), b = Math.max(editor.getSelectionEnd(), 0);
        editor.getText().replace(Math.min(a, b), Math.max(a, b), s);
    }

    void updateStatus(String s) { status.setText(currentName + ".echo  ·  " + s); }

    // ------------------------------------------------------------------ highlighting
    void highlight() {
        highlighting = true;
        Editable e = editor.getText();
        for (ForegroundColorSpan sp : e.getSpans(0, e.length(), ForegroundColorSpan.class)) e.removeSpan(sp);
        if (e.length() < 60000) {
            String t = e.toString();
            paint(e, P_NUMBER.matcher(t), NUMBER);
            paint(e, P_KEYWORD.matcher(t), KEYWORD);
            paint(e, P_BIO.matcher(t), BIO);
            paint(e, P_STRING.matcher(t), STRING);
            paint(e, P_COMMENT.matcher(t), COMMENT);
        }
        highlighting = false;
    }

    void paint(Editable e, Matcher m, int color) {
        while (m.find()) e.setSpan(new ForegroundColorSpan(color), m.start(), m.end(), Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
    }

    // ------------------------------------------------------------------ running
    void runOrStop() {
        if (running) { stopRequested = true; updateStatus("Stopping…"); return; }
        final String code = editor.getText().toString();
        output.setText("");
        running = true;
        stopRequested = false;
        runBtn.setText("■ Stop");
        updateStatus("Running…");
        final Bridge bridge = new Bridge();
        final String provider = prefs.getString("ai_provider", ""), key = prefs.getString("ai_key", ""),
                model = prefs.getString("ai_model", "");
        final long start = System.currentTimeMillis();
        bridge.startMillis = start;
        Thread t = new Thread(null, () -> app.callAttr("run", code, bridge, getFilesDir().getAbsolutePath(), provider, key, model),
                "echo-run", 256L * 1024 * 1024);
        t.start();
    }

    /** Called from Python. Public methods are visible to the interpreter. */
    public class Bridge {
        long startMillis;
        boolean failed = false;

        public void say(String text) { append(text + "\n", false); }

        public void error(String text) { failed = true; append(text + "\n", true); }

        public boolean stopRequested() { return stopRequested; }

        public String ask(final String prompt) {
            flush();
            final String[] answer = {""};
            final CountDownLatch latch = new CountDownLatch(1);
            ui.post(() -> {
                final EditText input = new EditText(MainActivity.this);
                input.setSingleLine(true);
                new AlertDialog.Builder(MainActivity.this)
                        .setTitle(prompt.trim())
                        .setView(input)
                        .setCancelable(false)
                        .setPositiveButton("OK", (d, w) -> { answer[0] = input.getText().toString(); latch.countDown(); })
                        .setNegativeButton("Stop", (d, w) -> { stopRequested = true; latch.countDown(); })
                        .show();
            });
            try { latch.await(); } catch (InterruptedException ignored) {}
            append(prompt + answer[0] + "\n", false);
            return answer[0];
        }

        public void done() {
            flush();
            final long ms = System.currentTimeMillis() - startMillis;
            ui.post(() -> {
                running = false;
                runBtn.setText("▶ Run");
                updateStatus((failed ? "Stopped with a problem" : "Done") + " in " + ms + " ms");
            });
        }
    }

    void append(String text, boolean isError) {
        synchronized (pending) {
            if (isError) pending.append("\u0001").append(text).append("\u0002");
            else pending.append(text);
            if (!flushScheduled) { flushScheduled = true; ui.postDelayed(this::flush, 80); }
        }
    }

    void flush() {
        final String chunk;
        synchronized (pending) {
            chunk = pending.toString();
            pending.setLength(0);
            flushScheduled = false;
        }
        if (chunk.isEmpty()) return;
        ui.post(() -> {
            int i = 0;
            while (i < chunk.length()) {
                int s = chunk.indexOf('\u0001', i);
                if (s < 0) { output.append(chunk.substring(i)); break; }
                output.append(chunk.substring(i, s));
                int e = chunk.indexOf('\u0002', s);
                if (e < 0) e = chunk.length();
                android.text.SpannableString sp = new android.text.SpannableString(chunk.substring(s + 1, e));
                sp.setSpan(new ForegroundColorSpan(ERROR), 0, sp.length(), 0);
                output.append(sp);
                i = e + 1;
            }
            if (output.length() > 200000) {
                CharSequence t = output.getText();
                output.setText(t.subSequence(t.length() - 150000, t.length()));
            }
            outputScroll.post(() -> outputScroll.fullScroll(View.FOCUS_DOWN));
        });
    }

    // ------------------------------------------------------------------ files
    File dir() {
        File d = new File(getFilesDir(), "programs");
        if (!d.exists()) d.mkdirs();
        return d;
    }

    void showExamples() {
        final List<PyObject> names = app.callAttr("examples").asList();
        final String[] items = new String[names.size()];
        for (int i = 0; i < items.length; i++) items[i] = names.get(i).toString();
        new AlertDialog.Builder(this).setTitle("Examples").setItems(items, (d, w) -> {
            editor.setText(app.callAttr("example", items[w]).toString());
            currentName = items[w];
            output.setText("");
            updateStatus("Example loaded. Tap ▶ Run.");
        }).show();
    }

    void showFiles() {
        final String[] files = dir().list((d, n) -> n.endsWith(".echo"));
        if (files == null || files.length == 0) { toast("No saved programs yet. Use Save."); return; }
        Arrays.sort(files);
        new AlertDialog.Builder(this).setTitle("Your programs").setItems(files, (d, w) -> {
            try {
                File f = new File(dir(), files[w]);
                byte[] data = new byte[(int) f.length()];
                try (FileInputStream in = new FileInputStream(f)) { int off = 0; while (off < data.length) { int r = in.read(data, off, data.length - off); if (r < 0) break; off += r; } }
                editor.setText(new String(data, StandardCharsets.UTF_8));
                currentName = files[w].substring(0, files[w].length() - 5);
                updateStatus("Opened.");
            } catch (Exception e) { toast("Can't open: " + e.getMessage()); }
        }).setNegativeButton("Close", null).show();
    }

    void saveAs() {
        final EditText name = new EditText(this);
        name.setText(currentName);
        name.setSingleLine(true);
        new AlertDialog.Builder(this).setTitle("Save as").setView(name).setPositiveButton("Save", (d, w) -> {
            String n = name.getText().toString().trim().replaceAll("[^A-Za-z0-9_\\- ]", "");
            if (n.isEmpty()) n = "program";
            try (FileOutputStream out = new FileOutputStream(new File(dir(), n + ".echo"))) {
                out.write(editor.getText().toString().getBytes(StandardCharsets.UTF_8));
                currentName = n;
                updateStatus("Saved.");
            } catch (Exception e) { toast("Can't save: " + e.getMessage()); }
        }).setNegativeButton("Cancel", null).show();
    }

    void newFile() {
        new AlertDialog.Builder(this).setMessage("Start a new program? Unsaved changes will be lost.")
                .setPositiveButton("New", (d, w) -> { editor.setText("# My Echo program\nsay \"Hello!\"\n"); currentName = "main"; output.setText(""); updateStatus("New program."); })
                .setNegativeButton("Cancel", null).show();
    }

    void shareCode() {
        Intent i = new Intent(Intent.ACTION_SEND);
        i.setType("text/plain");
        i.putExtra(Intent.EXTRA_SUBJECT, currentName + ".echo");
        i.putExtra(Intent.EXTRA_TEXT, editor.getText().toString());
        startActivity(Intent.createChooser(i, "Share Echo code"));
    }

    // ------------------------------------------------------------------ tools
    void convert(boolean java) {
        String code = editor.getText().toString();
        String cls = currentName.replaceAll("[^A-Za-z0-9_]", "");
        final String result = java ? app.callAttr("to_java", code, cls.isEmpty() ? "Program" : cls).toString()
                : app.callAttr("to_python", code).toString();
        AlertDialog.Builder b = new AlertDialog.Builder(this).setTitle(java ? "Echo → Java" : "Echo → Python")
                .setView(codeView(result))
                .setPositiveButton("Copy", (d, w) -> copy(result))
                .setNeutralButton("Share", (d, w) -> {
                    Intent i = new Intent(Intent.ACTION_SEND);
                    i.setType("text/plain");
                    i.putExtra(Intent.EXTRA_TEXT, result);
                    startActivity(Intent.createChooser(i, "Share code"));
                });
        if (java) b.setNegativeButton("Copy runtime", (d, w) -> copy(app.callAttr("java_runtime").toString()));
        else b.setNegativeButton("Close", null);
        b.show();
    }

    View codeView(String text) {
        TextView t = new TextView(this);
        t.setText(text);
        t.setTypeface(Typeface.MONOSPACE);
        t.setTextSize(11);
        t.setTextIsSelectable(true);
        t.setPadding(dp(14), dp(10), dp(14), dp(10));
        HorizontalScrollView h = new HorizontalScrollView(this);
        h.addView(t);
        ScrollView s = new ScrollView(this);
        s.addView(h);
        return s;
    }

    void checkCode() {
        String err = app.callAttr("check", editor.getText().toString()).toString();
        if (err.isEmpty()) toast("No problems found ✓");
        else new AlertDialog.Builder(this).setTitle("Problem").setMessage(err).setPositiveButton("OK", null).show();
    }

    void showGuide() {
        new AlertDialog.Builder(this).setTitle("Echo guide")
                .setView(codeView(app.callAttr("reference").toString()))
                .setPositiveButton("Close", null).show();
    }

    void aiSettings() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(18), dp(8), dp(18), 0);
        final String[] providers = {"claude", "gemini", "openai"};
        final Spinner sp = new Spinner(this);
        sp.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, providers));
        sp.setSelection(Math.max(0, Arrays.asList(providers).indexOf(prefs.getString("ai_provider", "claude"))));
        final EditText key = new EditText(this);
        key.setHint("API key");
        key.setText(prefs.getString("ai_key", ""));
        key.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        final EditText model = new EditText(this);
        model.setHint("Model (optional)");
        model.setText(prefs.getString("ai_model", ""));
        TextView note = new TextView(this);
        note.setText("Your key is saved only on this phone. Nothing is sent until your program runs ai(), ai_code(), ai_explain() or ask ai.");
        note.setTextSize(12);
        box.addView(sp);
        box.addView(key);
        box.addView(model);
        box.addView(note);
        new AlertDialog.Builder(this).setTitle("AI key").setView(box)
                .setPositiveButton("Save", (d, w) -> {
                    prefs.edit().putString("ai_provider", providers[sp.getSelectedItemPosition()])
                            .putString("ai_key", key.getText().toString().trim())
                            .putString("ai_model", model.getText().toString().trim()).apply();
                    toast("AI settings saved");
                })
                .setNeutralButton("Remove key", (d, w) -> { prefs.edit().remove("ai_key").apply(); toast("Key removed"); })
                .setNegativeButton("Cancel", null).show();
    }

    void copy(String text) {
        ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        cm.setPrimaryClip(ClipData.newPlainText("echo", text));
        toast("Copied");
    }

    void toast(String s) { Toast.makeText(this, s, Toast.LENGTH_SHORT).show(); }
}
