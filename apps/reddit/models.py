from django.db import models

# Create your models here.


#1. models (supports fast/medium/slow polling tiers.)

class Subreddit(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField()

    def __str__(self):
        return self.name

    class Meta:
        db_table = "subreddits"
        managed = False



#2.stores data for analytics

# class Post(models.Model):
#     reddit_id = models.CharField(max_length=50, unique=True)
#     subreddit = models.ForeignKey(Subreddit, on_delete=models.CASCADE)
#     title = models.TextField()
#     author = models.CharField(max_length=100)
#     score = models.IntegerField()
#     upvote_ratio = models.FloatField(null=True, blank=True)
#     num_comments = models.IntegerField(default=0)
#     created_utc = models.DateTimeField()
#     fetched_at = models.DateTimeField(auto_now=True)
#
#     class Meta:
#         db_table = "posts"

class Post(models.Model):
    id = models.CharField(primary_key=True, max_length=20)
    subreddit = models.ForeignKey(Subreddit, on_delete=models.CASCADE)

    title = models.TextField()
    author = models.CharField(max_length=100)
    created_utc = models.DateTimeField()

    first_seen_at = models.DateTimeField(null=True, blank=True)
    last_polled_at = models.DateTimeField(null=True, blank=True)

    current_score = models.IntegerField()
    current_comments = models.IntegerField()
    current_ratio = models.FloatField()

    poll_priority = models.CharField(max_length=20, null=True, blank=True)
    is_active = models.BooleanField()

    #velocity = models.FloatField(null=True, blank=True)
    #trending_score = models.FloatField(null=True, blank=True)


    class Meta:
        db_table = "posts"
        managed = False



#3.comments - likey need more change later

class Comment(models.Model):
    reddit_id = models.CharField(max_length=50, unique=True)
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    author = models.CharField(max_length=100)
    body = models.TextField()
    score = models.IntegerField()
    sentiment = models.FloatField(null=True, blank=True)
    created_utc = models.DateTimeField()


#4. trending keywords search (basic - later experiment with ML)

class KeywordTrend(models.Model):
    keyword = models.CharField(max_length=100)
    subreddit = models.ForeignKey(Subreddit, on_delete=models.CASCADE)
    score = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)


#5. subreddits stats

class SubredditStats(models.Model):
    subreddit = models.ForeignKey(Subreddit, on_delete=models.CASCADE)
    date = models.DateField()
    total_posts = models.IntegerField()
    total_comments = models.IntegerField()
    top_user = models.CharField(max_length=100, null=True, blank=True)



