import datetime
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.shortcuts import reverse
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from .entry import Entry
from .category import Category

class AuthorNickValidator(UnicodeUsernameValidator):
    regex = r'^[a-z\ ]+$'
    message = _("boşluk dışında türkçe ve özel karakter içermeyen alfabe harflerinden oluşan bir nick münasiptir")


class Author(AbstractUser):
    # genders
    MAN = 'MN'
    WOMAN = 'WM'
    OTHER = 'OT'
    UNKNOWN = 'NO'
    GENDERS = ((MAN, 'erkek'), (WOMAN, 'kadın'), (OTHER, 'diğer'), (UNKNOWN, 'boşver'))

    # entry/topic per page preference
    TEN = 10
    THIRTY = 30
    FIFTY = 50
    SEVENTYFIVE = 75
    ONEHUNDRED = 100
    ENTRY_COUNTS = ((TEN, "10"), (THIRTY, "30"), (FIFTY, "50"), (ONEHUNDRED, "100"))
    TOPIC_COUNTS = ((THIRTY, "30"), (FIFTY, "50"), (SEVENTYFIVE, "75"), (ONEHUNDRED, "100"))

    # status of author queue
    PENDING = "PN"
    ON_HOLD = "OH"
    APPROVED = "AP"
    APPLICATION_STATUS = (
        (PENDING, "çaylak listesinde"), (ON_HOLD, "entry girmesi bekleniyor"), (APPROVED, "yazar oldu"))

    #  recieving messages preference
    DISABLED = "DS"
    ALL_USERS = "AU"
    AUTHOR_ONLY = "AO"
    FOLLOWING_ONLY = "FO"
    MESSAGE_PREFERENCE = ((DISABLED, "hiçkimse"), (ALL_USERS, "yazar ve çaylaklar"), (AUTHOR_ONLY, "yazarlar"),
                          (FOLLOWING_ONLY, "takip ettiklerim"))

    nick_validator = AuthorNickValidator()
    username = models.CharField(_('username'), max_length=50, unique=True, help_text=_(
        'şart. en fazla 50 karakter uzunluğunda, boşluk içerebilir özel ve türkçe karakter içeremez'),
                                validators=[nick_validator], error_messages={'unique': _("bu nick kapılmış"), }, )

    birth_date = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=2, choices=GENDERS, default=UNKNOWN)
    is_novice = models.BooleanField(default=True)
    is_active = models.BooleanField(default=False)
    application_status = models.CharField(max_length=2, choices=APPLICATION_STATUS, default=ON_HOLD)
    application_date = models.DateTimeField(null=True, blank=True, default=None)
    last_activity = models.DateTimeField(null=True, blank=True, default=None)  # NOT NULL
    banned_until = models.DateTimeField(null=True, blank=True, default=None)
    following = models.ManyToManyField("self", blank=True, symmetrical=False, related_name="+")
    blocked = models.ManyToManyField("self", blank=True, symmetrical=False, related_name="+")
    entries_per_page = models.IntegerField(choices=ENTRY_COUNTS, default=TEN)
    topics_per_page = models.IntegerField(choices=TOPIC_COUNTS, default=FIFTY)
    message_preference = models.CharField(max_length=2, choices=MESSAGE_PREFERENCE, default=ALL_USERS)
    favorite_entries = models.ManyToManyField('Entry', related_name="favorited_by", blank=True)
    upvoted_entries = models.ManyToManyField('Entry', related_name="upvoted_by", blank=True)
    downvoted_entries = models.ManyToManyField('Entry', related_name="downvoted_by", blank=True)
    pinned_entry = models.OneToOneField('Entry', blank=True, null=True, on_delete=models.SET_NULL, related_name="+")
    following_categories = models.ManyToManyField('Category', blank=True)
    email = models.EmailField(_('e-posta adresi'), unique=True)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']  # notice: username field will be used for nicknames

    def __str__(self):
        return f"{self.username}:{self.id}"

    def save(self, *args, **kwargs):
        created = self.pk is None
        super().save(*args, **kwargs)
        if created:
            # newly created user
            categories_list = list(Category.objects.all())
            self.following_categories.add(*categories_list)

    def get_absolute_url(self):
        # todo use This!
        return reverse("user-profile", kwargs={"username": self.username})

    class Meta:
        # Superusers need to have this permission to accept a novice as an author.
        permissions = (("can_activate_user", "Make author"),)
        verbose_name = "yazar"
        verbose_name_plural = "yazarlar"

    @property
    def entry_count(self):
        return Entry.objects_published.filter(author=self).count()

    @property
    def entry_count_month(self):
        return Entry.objects_published.filter(author=self,
                                              date_created__gte=timezone.now() - datetime.timedelta(days=30)).count()

    @property
    def entry_count_week(self):
        return Entry.objects_published.filter(author=self,
                                              date_created__gte=timezone.now() - datetime.timedelta(days=7)).count()

    @property
    def entry_count_day(self):
        return Entry.objects_published.filter(author=self,
                                              date_created__gte=timezone.now() - datetime.timedelta(days=1)).count()

    @property
    def last_entry_date(self):
        try:
            return Entry.objects_published.filter(author=self).latest("date_created").date_created
        except Entry.DoesNotExist:
            return None

    @property
    def followers(self):
        return Author.objects.filter(following=self)

    @property
    def entry_nice(self):
        entry = Entry.objects_published.filter(author=self).order_by("-vote_rate").first()
        if entry and entry.vote_rate > Decimal("1"):
            return entry
        return None

    @property
    def email_confirmed(self):
        if self.userverification_set.filter(
                expiration_date__gte=timezone.now() - datetime.timedelta(hours=24)).exists():
            return False
        return True


class Memento(models.Model):
    body = models.TextField(blank=True, null=True)
    holder = models.ForeignKey(Author, on_delete=models.CASCADE)
    patient = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=['holder', 'patient'], name='unique_memento')]

    def __str__(self):
        return f"{self.__class__.__name__}#{self.id}, from {self.holder} about {self.patient}"


class UserVerification(models.Model):
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    verification_token = models.CharField(max_length=128)
    new_email = models.EmailField(null=True, blank=True)  # new e-mail if it is subject to change
    expiration_date = models.DateTimeField()

    def save(self, *args, **kwargs):
        UserVerification.objects.filter(author=self.author).delete()
        super().save(*args, **kwargs)
