# SPDX-License-Identifier: Apache-2.0
"""Coverage/restart reporting must not turn disconnects into successful tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
P=Path(__file__).resolve().parents[1]/'tools/muse/soak.py'
spec=importlib.util.spec_from_file_location('muse_soak',P);soak=importlib.util.module_from_spec(spec);spec.loader.exec_module(soak)
META={'start_at':1000,'end_at':4600,'interval_seconds':60}
def sample(at,uptime,free=42000):return {'at':at,'ok':True,'wifi':'connected','muse':'Connected','link':'Online','power':{'uptime':uptime,'boot':'power on','heap':{'free':free,'largest':30000}}}
class Soak(unittest.TestCase):
 def test_healthy_coverage(self):
  s=soak.summarize([sample(1000,60),sample(1060,120),sample(1120,180)],META,1120)
  self.assertEqual(s['observed_seconds'],120);self.assertEqual(s['coverage_fraction'],1);self.assertFalse(s['restart_events']);self.assertFalse(s['window_complete'])
 def test_missing_device_is_gap(self):
  s=soak.summarize([sample(1000,60),{'at':1060,'ok':False,'reason':'usb_absent'},sample(1120,180)],META,1120)
  self.assertEqual(s['observed_seconds'],0);self.assertEqual(s['unavailable_samples'],1);self.assertEqual(s['successful_samples'],2)
 def test_restart(self):
  s=soak.summarize([sample(1000,900),sample(1060,5)],META,1060)
  self.assertEqual(len(s['restart_events']),1);self.assertEqual(s['observed_seconds'],0)
 def test_host_sleep_does_not_imply_reset(self):
  s=soak.summarize([sample(1000,900),sample(4000,3900)],META,4000)
  self.assertFalse(s['possible_restarts_across_gaps']);self.assertEqual(s['observed_seconds'],0)
 def test_reset_across_gap(self):
  s=soak.summarize([sample(1000,900),sample(4000,20)],META,4000)
  self.assertEqual(len(s['possible_restarts_across_gaps']),1)
 def test_end_window_is_not_success_claim(self):
  s=soak.summarize([{'at':1000,'ok':False}],META,4601)
  self.assertTrue(s['window_complete']);self.assertTrue(s['stale']);self.assertEqual(s['coverage_fraction'],0);self.assertIsNone(s['internal_heap_min_sampled'])
 def test_only_known_power_fields(self):
  p=soak.safe_power({'uptime':8,'token':'PRIVATE','ssid':'PRIVATE'});self.assertEqual(p,{'uptime':8})
 def test_partial_host_write(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'samples';p.write_text('{"ok":true}\n{"unfinished"')
   self.assertEqual(soak.load_samples(p),[{'ok':True}])
 def test_memory_and_offline(self):
  a=sample(1000,60,42000);b=sample(1060,120,40000);b['muse']='Disconnected'
  s=soak.summarize([a,b],META,1060);self.assertEqual(s['internal_heap_min_sampled'],40000);self.assertEqual(s['connection_not_online_samples'],1)

 def test_restart_during_short_usb_gap(self):
  s=soak.summarize([sample(1000,900),{'at':1060,'ok':False},sample(1120,10)],META,1120)
  self.assertEqual(len(s['possible_restarts_across_gaps']),1)
 def test_missing_port_classified_without_private_error(self):
  class Missing(Exception):pass
  def missing(*args):raise Missing('PRIVATE')
  with patch.dict('sys.modules',{'ports':SimpleNamespace(find=missing,NotFound=Missing),
      'chat':SimpleNamespace(Board=None),'power':SimpleNamespace(ask=None)}):
   s=soak.collect('serial','firmware')
  self.assertEqual(s['reason'],'usb_absent');self.assertNotIn('PRIVATE',str(s))
