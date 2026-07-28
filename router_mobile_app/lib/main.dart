// lib/main.dart
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

/// Base URL of your backend API (adjust as needed)
const String API_BASE = "http://10.0.2.2:5000";
// Note: use 10.0.2.2 for Android emulator to reach host machine;
// use localhost for web or replace with actual server IP.

void main() {
  runApp(RouterDashboardApp());
}

class RouterDashboardApp extends StatelessWidget {
  const RouterDashboardApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Router Dashboard',
      theme: ThemeData(primarySwatch: Colors.indigo),
      home: DashboardHome(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class DashboardHome extends StatefulWidget {
  const DashboardHome({super.key});

  @override
  _DashboardHomeState createState() => _DashboardHomeState();
}

class _DashboardHomeState extends State<DashboardHome> {
  Map<String, dynamic> config = {};
  List<dynamic> firewall = [];
  bool loading = true;

  @override
  void initState() {
    super.initState();
    refreshAll();
  }

  Future<void> refreshAll() async {
    setState(() => loading = true);
    await Future.wait([fetchConfig(), fetchFirewall()]);
    setState(() => loading = false);
  }

  Future<void> fetchConfig() async {
    try {
      final res = await http.get(Uri.parse("$API_BASE/config"));
      if (res.statusCode == 200) {
        setState(() {
          config = json.decode(res.body) as Map<String, dynamic>;
        });
      } else {
        debugPrint("fetchConfig failed: ${res.statusCode}");
      }
    } catch (e) {
      debugPrint("fetchConfig error: $e");
    }
  }

  Future<void> fetchFirewall() async {
    try {
      final res = await http.get(Uri.parse("$API_BASE/firewall"));
      if (res.statusCode == 200) {
        setState(() {
          firewall = json.decode(res.body) as List<dynamic>;
        });
      } else {
        debugPrint("fetchFirewall failed: ${res.statusCode}");
        setState(() => firewall = []);
      }
    } catch (e) {
      debugPrint("fetchFirewall error: $e");
      setState(() => firewall = []);
    }
  }

  Future<void> updateConfigValue(String key, dynamic value) async {
    try {
      final res = await http.put(
        Uri.parse("$API_BASE/config/$key"),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'value': value}),
      );
      if (res.statusCode == 200) {
        await fetchConfig();
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Updated $key')));
      } else {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Failed to update $key')));
      }
    } catch (e) {
      debugPrint("updateConfig error: $e");
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Error: $e')));
    }
  }

  Future<void> addFirewallRule(Map<String, String> rule) async {
    try {
      final res = await http.post(
        Uri.parse("$API_BASE/firewall"),
        headers: {'Content-Type': 'application/json'},
        body: json.encode(rule),
      );
      if (res.statusCode == 200 || res.statusCode == 201) {
        await fetchFirewall();
        Navigator.of(context).pop(); // close dialog
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Rule added')));
      } else {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Failed to add rule')));
      }
    } catch (e) {
      debugPrint("addFirewallRule error: $e");
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Error: $e')));
    }
  }

  Future<void> deleteFirewallRule(String id) async {
    try {
      final res = await http.delete(Uri.parse("$API_BASE/firewall/$id"));
      if (res.statusCode == 200) {
        await fetchFirewall();
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Rule deleted')));
      } else {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Failed to delete rule')));
      }
    } catch (e) {
      debugPrint("deleteFirewallRule error: $e");
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Error: $e')));
    }
  }

  void showEditValueDialog(String key, dynamic value) {
    final controller = TextEditingController(text: value?.toString() ?? '');
    showDialog(
      context: context,
      builder:
          (_) => AlertDialog(
            title: Text('Edit $key'),
            content: TextField(
              controller: controller,
              decoration: InputDecoration(labelText: key),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: Text('Cancel'),
              ),
              ElevatedButton(
                onPressed: () {
                  updateConfigValue(key, controller.text);
                },
                child: Text('Save'),
              ),
            ],
          ),
    );
  }

  void showAddRuleDialog() {
    final idCtrl = TextEditingController();
    final actionCtrl = TextEditingController();
    final srcCtrl = TextEditingController();
    final dstCtrl = TextEditingController();

    showDialog(
      context: context,
      builder:
          (_) => AlertDialog(
            title: Text('Add Firewall Rule'),
            content: SingleChildScrollView(
              child: Column(
                children: [
                  TextField(
                    controller: idCtrl,
                    decoration: InputDecoration(labelText: 'ID'),
                  ),
                  TextField(
                    controller: actionCtrl,
                    decoration: InputDecoration(
                      labelText: 'Action (ALLOW/DENY)',
                    ),
                  ),
                  TextField(
                    controller: srcCtrl,
                    decoration: InputDecoration(labelText: 'Source (IP/CIDR)'),
                  ),
                  TextField(
                    controller: dstCtrl,
                    decoration: InputDecoration(labelText: 'Destination'),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: Text('Cancel'),
              ),
              ElevatedButton(
                onPressed: () {
                  final rule = {
                    'id': idCtrl.text.trim(),
                    'action': actionCtrl.text.trim(),
                    'source': srcCtrl.text.trim(),
                    'destination': dstCtrl.text.trim(),
                  };
                  addFirewallRule(rule);
                },
                child: Text('Add'),
              ),
            ],
          ),
    );
  }

  Widget buildConfigCard() {
    final entries = config.entries.toList();
    return Card(
      elevation: 6,
      margin: EdgeInsets.all(12),
      child: Padding(
        padding: EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Router Configuration',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 10),
            ...entries.map((e) {
              // ignore nested objects for simple display
              final key = e.key;
              final val =
                  (e.value is String || e.value is num || e.value is bool)
                      ? e.value
                      : json.encode(e.value);
              return ListTile(
                title: Text(key),
                subtitle: Text(val.toString()),
                trailing: IconButton(
                  icon: Icon(Icons.edit),
                  onPressed: () => showEditValueDialog(key, val),
                ),
              );
            }),
          ],
        ),
      ),
    );
  }

  Widget buildFirewallCard() {
    return Card(
      elevation: 6,
      margin: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Padding(
        padding: EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Firewall Rules',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
                ElevatedButton.icon(
                  icon: Icon(Icons.add),
                  label: Text('Add'),
                  onPressed: showAddRuleDialog,
                ),
              ],
            ),
            SizedBox(height: 10),
            firewall.isEmpty
                ? Text('No rules found.')
                : Column(
                  children:
                      firewall.map((r) {
                        final id = r['id']?.toString() ?? '';
                        final action = r['action'] ?? '';
                        final src = r['source'] ?? '';
                        final dst = r['destination'] ?? '';
                        return ListTile(
                          title: Text('$id - $action'),
                          subtitle: Text('$src → $dst'),
                          trailing: IconButton(
                            icon: Icon(Icons.delete, color: Colors.red),
                            onPressed: () => deleteFirewallRule(id),
                          ),
                        );
                      }).toList(),
                ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Router Dashboard'),
        actions: [IconButton(icon: Icon(Icons.refresh), onPressed: refreshAll)],
      ),
      body:
          loading
              ? Center(child: CircularProgressIndicator())
              : RefreshIndicator(
                onRefresh: refreshAll,
                child: ListView(
                  children: [
                    buildConfigCard(),
                    buildFirewallCard(),
                    SizedBox(height: 20),
                    Padding(
                      padding: EdgeInsets.symmetric(horizontal: 12),
                      child: Text(
                        'Sample firewall rules (for testing):\n1) ALLOW 192.168.1.0/24 → ANY\n2) DENY ANY → 192.168.1.1\n3) ALLOW 192.168.1.50 → 10.0.0.10:22',
                        style: TextStyle(color: Colors.grey[700]),
                      ),
                    ),
                    SizedBox(height: 40),
                  ],
                ),
              ),
    );
  }
}
