import sqlite3,unittest
from scripts.haruq_backtest_2023 import HistoryGuard,netid,settle

class BacktestContracts(unittest.TestCase):
    def test_archive_id(self):
        self.assertEqual(netid('1120230427020006'),'202304281106')
    def test_unverified_is_not_loss(self):
        x=settle(['1>2>3'],100,{},'sanrentan',(1,2,3))
        self.assertIsNone(x['returned_yen'])
        self.assertEqual(x['status'],'unverified_settlement')
    def test_all_tickets_costed(self):
        x=settle(['1>2>3','2>1>3'],100,
            {'sanrentan_combo':'1-2-3','sanrentan_payout':2030},'sanrentan',(1,2,3))
        self.assertEqual((x['investment_yen'],x['returned_yen']),(200,2030))
        bad=settle(['1>2>3'],100,{'sanrentan_combo':'2-1-3','sanrentan_payout':2030},'sanrentan',(1,2,3))
        self.assertEqual(bad['status'],'unverified_settlement')
    def test_current_result_blocked(self):
        guard=HistoryGuard(sqlite3.connect(':memory:'),'2023-01-01')
        with self.assertRaises(RuntimeError):
            guard.execute('SELECT * FROM race_results WHERE race_id=?',('202301011101',))
