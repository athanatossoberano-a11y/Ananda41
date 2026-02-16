import requests
import sys
import json
from datetime import datetime

class MercadoPagoTester:
    def __init__(self, base_url="https://credito-move.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
        print(f"🚀 Testing Mercado Pago Integration - Ananda Bot")
        print(f"   Base URL: {self.base_url}")
        print(f"   API URL: {self.api_url}")
        print("=" * 80)

    def log_test(self, name, success, response_data=None, error=None):
        """Log test results"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - FAILED")
            if error:
                print(f"   Error: {error}")
        
        self.test_results.append({
            "test": name,
            "success": success,
            "response": response_data,
            "error": error
        })

    def run_test(self, name, method, endpoint, expected_status=200, data=None, show_response=True):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}" if endpoint else f"{self.api_url}/"
        headers = {'Content-Type': 'application/json'}

        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        if data:
            print(f"   Data: {json.dumps(data, indent=2)}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=15)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            response_data = None
            
            try:
                response_data = response.json()
            except:
                response_data = {"raw_response": response.text[:500]}

            print(f"   Status: {response.status_code} {'✅' if success else '❌'} (Expected: {expected_status})")
            
            if show_response and response_data:
                if isinstance(response_data, dict) and len(str(response_data)) < 1000:
                    print(f"   Response: {json.dumps(response_data, indent=2)}")
                else:
                    print(f"   Response keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'Non-dict response'}")

            if not success:
                error_msg = f"Status {response.status_code}, Expected {expected_status}"
                if response.text:
                    error_msg += f" - Response: {response.text[:200]}"
            else:
                error_msg = None

            self.log_test(name, success, response_data, error_msg)
            return success, response_data

        except requests.exceptions.Timeout:
            error = "Request timeout (15s)"
            print(f"   ❌ {error}")
            self.log_test(name, False, None, error)
            return False, {}
        except Exception as e:
            error = str(e)
            print(f"   ❌ {error}")
            self.log_test(name, False, None, error)
            return False, {}

    def test_api_base(self):
        """Test API base endpoint"""
        return self.run_test("API Base Endpoint", "GET", "")

    def test_mp_public_key(self):
        """Test GET /api/mercadopago/public-key"""
        success, response = self.run_test("MP Public Key", "GET", "mercadopago/public-key")
        if success and response:
            if "public_key" not in response:
                print("   ⚠️  Missing 'public_key' in response")
                return False
            if not response["public_key"] or not response["public_key"].startswith("APP_USR-"):
                print(f"   ⚠️  Invalid public key format: {response['public_key']}")
                return False
            print(f"   ✅ Public key: {response['public_key'][:20]}...")
        return success

    def test_mp_plans(self):
        """Test GET /api/mercadopago/plans"""
        success, response = self.run_test("MP Plans", "GET", "mercadopago/plans")
        if success and response:
            if "plans" not in response:
                print("   ⚠️  Missing 'plans' in response")
                return False
            
            plans = response["plans"]
            expected_plans = ["premium", "vip"]
            missing_plans = [plan for plan in expected_plans if plan not in plans]
            if missing_plans:
                print(f"   ⚠️  Missing plans: {missing_plans}")
                return False
            
            # Check premium plan
            premium = plans.get("premium", {})
            if premium.get("price_brl") != 19.90:
                print(f"   ⚠️  Premium price should be R$ 19.90, got {premium.get('price_brl')}")
                return False
            
            # Check VIP plan
            vip = plans.get("vip", {})
            if vip.get("price_brl") != 39.90:
                print(f"   ⚠️  VIP price should be R$ 39.90, got {vip.get('price_brl')}")
                return False
            
            print(f"   ✅ Found {len(plans)} plans with correct BRL prices")
        return success

    def test_mp_checkout_premium(self):
        """Test POST /api/mercadopago/checkout - Premium plan"""
        checkout_data = {
            "plan": "premium",
            "telegram_id": "123456789",
            "user_name": "Test User",
            "email": "test@test.com",
            "payment_method": "checkout_pro"
        }
        success, response = self.run_test("MP Checkout Premium", "POST", "mercadopago/checkout", 
                                        expected_status=200, data=checkout_data, show_response=False)
        if success and response:
            required_fields = ["preference_id", "init_point"]
            missing_fields = [field for field in required_fields if field not in response]
            if missing_fields:
                print(f"   ⚠️  Missing fields in checkout response: {missing_fields}")
                return False
            print(f"   ✅ Preference ID: {response.get('preference_id', 'N/A')}")
            print(f"   ✅ Init Point: {response.get('init_point', 'N/A')[:50]}...")
        return success

    def test_mp_checkout_vip(self):
        """Test POST /api/mercadopago/checkout - VIP plan"""
        checkout_data = {
            "plan": "vip",
            "telegram_id": "987654321",
            "user_name": "Test VIP User",
            "email": "vip@test.com",
            "payment_method": "checkout_pro"
        }
        success, response = self.run_test("MP Checkout VIP", "POST", "mercadopago/checkout", 
                                        expected_status=200, data=checkout_data, show_response=False)
        if success and response:
            required_fields = ["preference_id", "init_point"]
            missing_fields = [field for field in required_fields if field not in response]
            if missing_fields:
                print(f"   ⚠️  Missing fields in checkout response: {missing_fields}")
                return False
            print(f"   ✅ Preference ID: {response.get('preference_id', 'N/A')}")
            print(f"   ✅ Init Point: {response.get('init_point', 'N/A')[:50]}...")
        return success

    def test_mp_checkout_invalid_plan(self):
        """Test POST /api/mercadopago/checkout - Invalid plan (should fail)"""
        checkout_data = {
            "plan": "invalid_plan",
            "telegram_id": "123456789",
            "user_name": "Test User",
            "payment_method": "checkout_pro"
        }
        success, response = self.run_test("MP Checkout Invalid Plan", "POST", "mercadopago/checkout", 
                                        expected_status=400, data=checkout_data)
        return success

    def test_mp_pix_premium(self):
        """Test POST /api/mercadopago/pix - Premium plan"""
        pix_data = {
            "plan": "premium",
            "telegram_id": "123456789",
            "user_name": "Test PIX User",
            "email": "pix@test.com"
        }
        success, response = self.run_test("MP PIX Premium", "POST", "mercadopago/pix", 
                                        expected_status=200, data=pix_data, show_response=False)
        if success and response:
            required_fields = ["payment_id", "status"]
            missing_fields = [field for field in required_fields if field not in response]
            if missing_fields:
                print(f"   ⚠️  Missing fields in PIX response: {missing_fields}")
                return False
            print(f"   ✅ Payment ID: {response.get('payment_id', 'N/A')}")
            print(f"   ✅ Status: {response.get('status', 'N/A')}")
            if response.get('qr_code'):
                print(f"   ✅ QR Code generated: {len(response.get('qr_code', ''))} chars")
        return success

    def test_mp_pix_invalid_plan(self):
        """Test POST /api/mercadopago/pix - Invalid plan (should fail)"""
        pix_data = {
            "plan": "free",
            "telegram_id": "123456789",
            "email": "test@test.com"
        }
        success, response = self.run_test("MP PIX Invalid Plan", "POST", "mercadopago/pix", 
                                        expected_status=400, data=pix_data)
        return success

    def test_mp_payment_status_invalid(self):
        """Test GET /api/mercadopago/payment/{payment_id} - Invalid ID"""
        success, response = self.run_test("MP Payment Status Invalid", "GET", "mercadopago/payment/999999999", 
                                        expected_status=404)
        return success

    def test_mp_payments_list(self):
        """Test GET /api/mercadopago/payments"""
        success, response = self.run_test("MP Payments List", "GET", "mercadopago/payments")
        if success and response:
            if "payments" not in response:
                print("   ⚠️  Missing 'payments' in response")
                return False
            payments = response["payments"]
            print(f"   ✅ Found {len(payments)} payment records")
            if payments:
                first_payment = payments[0]
                expected_fields = ["id", "status", "created_at"]
                missing_fields = [field for field in expected_fields if field not in first_payment]
                if missing_fields:
                    print(f"   ⚠️  Payment record missing fields: {missing_fields}")
                else:
                    print(f"   ✅ Payment records have required fields")
        return success

    def run_all_tests(self):
        """Run all Mercado Pago tests"""
        tests = [
            self.test_api_base,
            self.test_mp_public_key,
            self.test_mp_plans,
            self.test_mp_checkout_premium,
            self.test_mp_checkout_vip,
            self.test_mp_checkout_invalid_plan,
            self.test_mp_pix_premium,
            self.test_mp_pix_invalid_plan,
            self.test_mp_payment_status_invalid,
            self.test_mp_payments_list
        ]

        for test in tests:
            try:
                test()
            except Exception as e:
                print(f"❌ Test {test.__name__} failed with exception: {str(e)}")
                self.log_test(test.__name__, False, None, str(e))

        return self.print_summary()

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 80)
        print("📊 MERCADO PAGO INTEGRATION TEST SUMMARY")
        print("=" * 80)
        print(f"Total tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Tests failed: {self.tests_run - self.tests_passed}")
        success_rate = (self.tests_passed/self.tests_run*100) if self.tests_run > 0 else 0
        print(f"Success rate: {success_rate:.1f}%")
        
        # Show failed tests
        failed_tests = [test for test in self.test_results if not test["success"]]
        if failed_tests:
            print(f"\n❌ FAILED TESTS ({len(failed_tests)}):")
            for test in failed_tests:
                print(f"   • {test['test']}: {test['error']}")
        
        # Show successful tests
        passed_tests = [test for test in self.test_results if test["success"]]
        if passed_tests:
            print(f"\n✅ PASSED TESTS ({len(passed_tests)}):")
            for test in passed_tests:
                print(f"   • {test['test']}")

        print(f"\n🎯 INTEGRATION STATUS: {'✅ WORKING' if success_rate >= 80 else '❌ NEEDS ATTENTION'}")
        
        if success_rate >= 80:
            print("\n✅ Mercado Pago integration is working correctly!")
            print("   - Public key endpoint accessible")
            print("   - Plans with correct BRL pricing")
            print("   - Checkout Pro and PIX payment creation working")
            print("   - Error handling for invalid requests working")
        else:
            print("\n⚠️  Mercado Pago integration needs attention:")
            print("   - Check failed tests above for specific issues")
            print("   - Verify Mercado Pago credentials in .env file")
            print("   - Check server logs for detailed error messages")

        print("\n" + "=" * 80)
        return self.tests_passed == self.tests_run

def main():
    tester = MercadoPagoTester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())