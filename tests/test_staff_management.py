from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from vps.audit.models import AuditLog

User = get_user_model()


class StaffManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="StrongPassword!2026",
            full_name="Lot Administrator",
            mobile="9876543210",
            role=User.Role.ADMIN,
        )

        self.attendant = User.objects.create_user(
            email="attendant@example.com",
            password="StrongPassword!2026",
            full_name="Gate Attendant",
            mobile="9876543211",
            role=User.Role.ATTENDANT,
        )

        self.staff_url = reverse("accounts:staff_list")
        self.deactivate_url = reverse(
            "accounts:deactivate_staff",
            args=[self.attendant.pk],
        )
        self.reactivate_url = reverse(
            "accounts:reactivate_staff",
            args=[self.attendant.pk],
        )

    def test_admin_can_view_staff_accounts(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.staff_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.attendant.email)

    def test_admin_can_deactivate_staff(self):
        self.client.force_login(self.admin)

        response = self.client.post(self.deactivate_url)

        self.assertRedirects(response, self.staff_url)

        self.attendant.refresh_from_db()
        self.assertFalse(self.attendant.is_active)

        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                action="staff.deactivated",
                target=f"user:{self.attendant.pk}",
            ).exists()
        )

    def test_admin_can_reactivate_staff(self):
        self.attendant.is_active = False
        self.attendant.save(update_fields=["is_active"])

        self.client.force_login(self.admin)

        response = self.client.post(self.reactivate_url)

        self.assertRedirects(response, self.staff_url)

        self.attendant.refresh_from_db()
        self.assertTrue(self.attendant.is_active)

        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                action="staff.reactivated",
                target=f"user:{self.attendant.pk}",
            ).exists()
        )

    def test_deactivation_invalidates_existing_staff_session(self):
        staff_client = self.client_class()
        staff_client.force_login(self.attendant)

        self.assertEqual(
            staff_client.session["_auth_user_id"],
            str(self.attendant.pk),
        )

        self.client.force_login(self.admin)
        self.client.post(self.deactivate_url)

        response = staff_client.get("/")

        self.assertRedirects(response, "/accounts/login/")

        self.assertNotIn("_auth_user_id", staff_client.session)

    def test_deactivated_staff_cannot_sign_in(self):
        self.attendant.is_active = False
        self.attendant.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("accounts:login"),
            {
                "email": self.attendant.email,
                "password": "StrongPassword!2026",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid e-mail or password")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_attendant_cannot_manage_staff(self):
        self.client.force_login(self.attendant)

        response = self.client.get(self.staff_url)

        self.assertEqual(response.status_code, 403)

    def test_driver_cannot_manage_staff(self):
        driver = User.objects.create_user(
            email="driver@example.com",
            password="StrongPassword!2026",
            full_name="Test Driver",
            mobile="9876543212",
            role=User.Role.DRIVER,
        )

        self.client.force_login(driver)

        response = self.client.get(self.staff_url)

        self.assertEqual(response.status_code, 403)

    def test_get_cannot_deactivate_staff(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.deactivate_url)

        self.assertEqual(response.status_code, 405)

        self.attendant.refresh_from_db()
        self.assertTrue(self.attendant.is_active)

    def test_repeated_deactivation_does_not_duplicate_audit(self):
        self.client.force_login(self.admin)

        self.client.post(self.deactivate_url)
        self.client.post(self.deactivate_url)

        self.assertEqual(
            AuditLog.objects.filter(
                action="staff.deactivated",
                target=f"user:{self.attendant.pk}",
            ).count(),
            1,
        )

    def test_admin_cannot_deactivate_own_account(self):
        """Self-deactivation could leave the lot with no administrator."""
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("accounts:deactivate_staff", args=[self.admin.pk]), follow=True
        )

        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertContains(response, "You cannot deactivate your own account.")
        self.assertFalse(AuditLog.objects.filter(action="staff.deactivated").exists())
        self.assertNotContains(
            response, reverse("accounts:deactivate_staff", args=[self.admin.pk])
        )
